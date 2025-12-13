"""
同步服务 - 处理笔记数据同步
"""
import json
import os
import sys
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse
from flask import current_app
import requests

# 将 Spider_XHS 目录添加到 sys.path，解决其内部相对导入问题
_spider_xhs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'Spider_XHS')
if _spider_xhs_path not in sys.path:
    sys.path.insert(0, _spider_xhs_path)

from ..extensions import db
from ..models import Account, Note, Cookie
from ..utils.logger import get_logger, log_sync_event
from ..config import Config
from Spider_XHS.xhs_utils.xhs_util import get_common_headers
from .sync_log_broadcaster import sync_log_broadcaster
from Spider_XHS.main import Data_Spider

# 获取日志器
logger = get_logger('sync')


class AdaptiveDelayManager:
    """智能延迟管理器 - 指数退避 + 快速恢复策略
    
    核心策略：
    1. 指数退避：每次限流后延迟翻倍（最高到 max_delay）
    2. 快速恢复：连续成功 N 次后延迟减半（最低到 min_delay）
    3. 动态调节：根据限流频率自动调整基础延迟
    """
    
    def __init__(
        self,
        min_delay: float = 5.0,
        max_delay: float = 300.0,
        initial_delay: float = 30.0,
        backoff_factor: float = 2.0,
        recovery_threshold: int = 3,
        recovery_factor: float = 0.7
    ):
        """
        Args:
            min_delay: Minimum delay in seconds
            max_delay: Maximum delay in seconds
            initial_delay: Starting delay value
            backoff_factor: Multiply delay by this on rate limit
            recovery_threshold: Consecutive successes needed to reduce delay
            recovery_factor: Multiply delay by this on recovery (< 1.0)
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.recovery_threshold = recovery_threshold
        self.recovery_factor = recovery_factor
        
        self._current_delay = initial_delay
        self._consecutive_success = 0
        self._rate_limit_count = 0
        self._lock = threading.Lock()
        
        logger.info(
            f"[AdaptiveDelay] Initialized: min={min_delay}s, max={max_delay}s, "
            f"initial={initial_delay}s, backoff={backoff_factor}x"
        )
    
    def record_rate_limit(self):
        """Record a rate limit event, increase delay exponentially"""
        with self._lock:
            self._rate_limit_count += 1
            self._consecutive_success = 0
            old_delay = self._current_delay
            self._current_delay = min(
                self._current_delay * self.backoff_factor,
                self.max_delay
            )
            logger.warning(
                f"[AdaptiveDelay] Rate limit #{self._rate_limit_count}: "
                f"delay {old_delay:.1f}s -> {self._current_delay:.1f}s"
            )
    
    def record_success(self):
        """Record a successful request, potentially reduce delay"""
        with self._lock:
            self._consecutive_success += 1
            
            # Fast recovery after consecutive successes
            if self._consecutive_success >= self.recovery_threshold:
                old_delay = self._current_delay
                self._current_delay = max(
                    self._current_delay * self.recovery_factor,
                    self.min_delay
                )
                self._consecutive_success = 0  # Reset counter
                
                if old_delay != self._current_delay:
                    logger.info(
                        f"[AdaptiveDelay] Fast recovery: "
                        f"delay {old_delay:.1f}s -> {self._current_delay:.1f}s"
                    )
    
    def get_delay(self) -> float:
        """Get current delay with random jitter (±20%)"""
        with self._lock:
            jitter = random.uniform(0.8, 1.2)
            return self._current_delay * jitter
    
    def get_rate_limit_wait(self) -> float:
        """Get wait time after rate limit (longer than normal delay)"""
        with self._lock:
            # Extra wait time based on consecutive rate limits
            base_wait = self._current_delay * 2
            extra_wait = min(self._rate_limit_count * 15, 120)
            return base_wait + extra_wait + random.uniform(5, 15)
    
    def reset(self):
        """Reset to initial state"""
        with self._lock:
            self._current_delay = self.initial_delay
            self._consecutive_success = 0
            self._rate_limit_count = 0
            logger.info("[AdaptiveDelay] Reset to initial state")
    
    def get_stats(self) -> dict:
        """Get current statistics"""
        with self._lock:
            return {
                'current_delay': self._current_delay,
                'consecutive_success': self._consecutive_success,
                'rate_limit_count': self._rate_limit_count,
            }


class RequestSessionPool:
    """HTTP 请求会话池 - 复用 TCP 连接提高性能
    
    使用 requests.Session 复用 TCP 连接的优点：
    1. 避免重复 TCP 三次握手
    2. 复用 SSL/TLS 会话
    3. 支持 HTTP Keep-Alive
    4. 连接池管理，避免连接泄漏
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Connection pool configuration
    POOL_CONNECTIONS = 10  # Number of connection pools to cache
    POOL_MAXSIZE = 10      # Max connections per host
    MAX_RETRIES = 3        # Automatic retries on connection errors
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Create session with connection pooling
        self._session = requests.Session()
        
        # Configure connection pool adapter
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.POOL_CONNECTIONS,
            pool_maxsize=self.POOL_MAXSIZE,
            max_retries=self.MAX_RETRIES,
            pool_block=False
        )
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
        
        # Statistics
        self._stats = {'requests': 0, 'errors': 0}
        self._stats_lock = threading.Lock()
        
        self._initialized = True
        logger.info(
            f"[RequestSessionPool] Initialized: "
            f"pool_connections={self.POOL_CONNECTIONS}, pool_maxsize={self.POOL_MAXSIZE}"
        )
    
    def get(self, url, **kwargs) -> requests.Response:
        """Send GET request using pooled session"""
        with self._stats_lock:
            self._stats['requests'] += 1
        
        try:
            return self._session.get(url, **kwargs)
        except Exception as e:
            with self._stats_lock:
                self._stats['errors'] += 1
            raise
    
    def post(self, url, **kwargs) -> requests.Response:
        """Send POST request using pooled session"""
        with self._stats_lock:
            self._stats['requests'] += 1
        
        try:
            return self._session.post(url, **kwargs)
        except Exception as e:
            with self._stats_lock:
                self._stats['errors'] += 1
            raise
    
    @property
    def session(self) -> requests.Session:
        """Get the underlying session for direct use"""
        return self._session
    
    def get_stats(self) -> dict:
        """Get request statistics"""
        with self._stats_lock:
            return self._stats.copy()
    
    def close(self):
        """Close all connections in the pool"""
        self._session.close()
        logger.info("[RequestSessionPool] Session pool closed")


# Global instances
_adaptive_delay_manager = None
_request_session_pool = None


def get_adaptive_delay_manager() -> AdaptiveDelayManager:
    """Get global adaptive delay manager instance"""
    global _adaptive_delay_manager
    if _adaptive_delay_manager is None:
        _adaptive_delay_manager = AdaptiveDelayManager()
    return _adaptive_delay_manager


def get_request_session_pool() -> RequestSessionPool:
    """Get global request session pool instance"""
    global _request_session_pool
    if _request_session_pool is None:
        _request_session_pool = RequestSessionPool()
    return _request_session_pool


class SyncLogCollector:
    """同步日志收集器 - 用于收集深度同步过程中的各类异常信息"""
    
    # 异常类型定义
    TYPE_RATE_LIMITED = 'rate_limited'       # 限流
    TYPE_UNAVAILABLE = 'unavailable'         # 笔记不可用
    TYPE_MISSING_FIELD = 'missing_field'     # 字段缺失（使用列表页数据回退）
    TYPE_FETCH_FAILED = 'fetch_failed'       # 获取失败
    TYPE_TOKEN_REFRESH = 'token_refresh'     # Token刷新
    TYPE_MEDIA_FAILED = 'media_failed'       # 媒体下载失败
    TYPE_AUTH_ERROR = 'auth_error'           # 认证错误
    
    def __init__(self, account_id, sync_mode='deep'):
        self.account_id = account_id
        self.sync_mode = sync_mode
        self.start_time = datetime.utcnow().isoformat() + 'Z'
        self.end_time = None
        self.issues = []  # 问题列表
        self.summary = {
            'total': 0,           # 总笔记数
            'success': 0,         # 成功数
            'rate_limited': 0,    # 限流次数
            'unavailable': 0,     # 不可用笔记数
            'missing_field': 0,   # 字段缺失（回退到列表页数据）
            'fetch_failed': 0,    # 获取失败数
            'token_refresh': 0,   # Token刷新次数
            'media_failed': 0,    # 媒体下载失败数
            'skipped': 0,         # 跳过（已有完整数据）
        }
        self._lock = threading.Lock()
    
    def add_issue(self, issue_type, note_id=None, message=None, fields=None, extra=None):
        """添加一个问题记录"""
        with self._lock:
            issue = {
                'type': issue_type,
                'time': datetime.utcnow().isoformat() + 'Z',
            }
            if note_id:
                issue['note_id'] = note_id
            if message:
                issue['message'] = message[:500]  # 限制消息长度
            if fields:
                issue['fields'] = fields
            if extra:
                issue['extra'] = extra
            
            # 限制问题列表最大长度，避免日志过大
            if len(self.issues) < 500:
                self.issues.append(issue)
            
            # 更新摘要计数
            if issue_type == self.TYPE_RATE_LIMITED:
                self.summary['rate_limited'] += 1
            elif issue_type == self.TYPE_UNAVAILABLE:
                self.summary['unavailable'] += 1
            elif issue_type == self.TYPE_MISSING_FIELD:
                self.summary['missing_field'] += 1
            elif issue_type == self.TYPE_FETCH_FAILED:
                self.summary['fetch_failed'] += 1
            elif issue_type == self.TYPE_TOKEN_REFRESH:
                self.summary['token_refresh'] += 1
            elif issue_type == self.TYPE_MEDIA_FAILED:
                self.summary['media_failed'] += 1
    
    def record_success(self):
        """记录一个成功处理的笔记"""
        with self._lock:
            self.summary['success'] += 1
    
    def record_skipped(self):
        """记录一个跳过的笔记（已有完整数据）"""
        with self._lock:
            self.summary['skipped'] += 1
    
    def set_total(self, total):
        """设置总笔记数"""
        with self._lock:
            self.summary['total'] = total
    
    def finalize(self):
        """完成日志收集，生成最终日志"""
        with self._lock:
            self.end_time = datetime.utcnow().isoformat() + 'Z'
            return {
                'sync_mode': self.sync_mode,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'summary': self.summary,
                'issues': self.issues,
            }
    
    def save_to_db(self):
        """保存日志到数据库"""
        try:
            logs_data = self.finalize()
            account = Account.query.get(self.account_id)
            if account:
                account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                db.session.commit()
                logger.info(f"同步日志已保存到账号 {self.account_id}")
        except Exception as e:
            logger.error(f"保存同步日志失败: {e}")
            db.session.rollback()


class MediaDownloadQueue:
    """异步媒体下载队列 - 使用线程池处理下载任务，避免阻塞主同步流程
    
    单例模式，全局共享一个下载队列。
    支持两种任务类型：
    1. cover - 封面下载
    2. media - 完整媒体文件下载
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Thread pool configuration
    MAX_WORKERS = 4  # Concurrent download threads
    QUEUE_TIMEOUT = 10  # Seconds to wait for task submission
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix='media_dl')
        self._futures = []
        self._futures_lock = threading.Lock()
        self._stats = {'submitted': 0, 'completed': 0, 'failed': 0}
        self._stats_lock = threading.Lock()
        self._initialized = True
        logger.info(f"[MediaDownloadQueue] Initialized with {self.MAX_WORKERS} workers")
    
    def submit_cover_download(self, remote_url, note_id, callback=None):
        """Submit a cover download task to the queue
        
        Args:
            remote_url: Remote URL of the cover image
            note_id: Note ID for filename generation
            callback: Optional callback function(note_id, local_path) called after download
        """
        if not remote_url or not note_id:
            return
        
        def _download_task():
            try:
                local_path = self._do_download_cover(remote_url, note_id)
                if callback and local_path:
                    callback(note_id, local_path)
                with self._stats_lock:
                    self._stats['completed'] += 1
                return local_path
            except Exception as e:
                logger.warning(f"[MediaDownloadQueue] Cover download failed for {note_id}: {e}")
                with self._stats_lock:
                    self._stats['failed'] += 1
                return None
        
        try:
            future = self._executor.submit(_download_task)
            with self._futures_lock:
                self._futures.append(future)
                with self._stats_lock:
                    self._stats['submitted'] += 1
        except Exception as e:
            logger.warning(f"[MediaDownloadQueue] Failed to submit cover task for {note_id}: {e}")
    
    def submit_media_download(self, note_id, note_data):
        """Submit a full media download task to the queue
        
        Args:
            note_id: Note ID
            note_data: Note data dict containing image_list and video_addr
        """
        if not note_id or not note_data:
            return
        
        def _download_task():
            try:
                self._do_download_all_media(note_id, note_data)
                with self._stats_lock:
                    self._stats['completed'] += 1
            except Exception as e:
                logger.warning(f"[MediaDownloadQueue] Media download failed for {note_id}: {e}")
                with self._stats_lock:
                    self._stats['failed'] += 1
        
        try:
            future = self._executor.submit(_download_task)
            with self._futures_lock:
                self._futures.append(future)
                with self._stats_lock:
                    self._stats['submitted'] += 1
        except Exception as e:
            logger.warning(f"[MediaDownloadQueue] Failed to submit media task for {note_id}: {e}")
    
    def wait_completion(self, timeout=None):
        """Wait for all pending download tasks to complete
        
        Args:
            timeout: Maximum seconds to wait. None means wait forever.
        
        Returns:
            bool: True if all tasks completed, False if timeout
        """
        with self._futures_lock:
            futures_copy = self._futures[:]
        
        if not futures_copy:
            return True
        
        try:
            completed = 0
            for future in as_completed(futures_copy, timeout=timeout):
                completed += 1
            
            # Clean up completed futures
            with self._futures_lock:
                self._futures = [f for f in self._futures if not f.done()]
            
            logger.info(f"[MediaDownloadQueue] Wait completed: {completed} tasks finished")
            return True
        except TimeoutError:
            logger.warning(f"[MediaDownloadQueue] Wait timeout after {timeout}s")
            return False
    
    def get_stats(self):
        """Get current queue statistics"""
        with self._stats_lock:
            pending = 0
            with self._futures_lock:
                pending = len([f for f in self._futures if not f.done()])
            return {
                'submitted': self._stats['submitted'],
                'completed': self._stats['completed'],
                'failed': self._stats['failed'],
                'pending': pending
            }
    
    def _do_download_cover(self, remote_url, note_id):
        """Actual cover download implementation (runs in worker thread)"""
        if not remote_url:
            return None
        try:
            Config.init_paths()
            parsed = urlparse(remote_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filename = f"{note_id}_cover{ext}"
            filepath = os.path.join(Config.MEDIA_PATH, filename)
            
            # Skip if file exists and is valid
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                return f"/api/media/{filename}"
            
            headers = get_common_headers()
            session_pool = get_request_session_pool()
            # Retry mechanism with shorter timeout for async downloads
            for attempt in range(2):
                try:
                    resp = session_pool.get(remote_url, headers=headers, stream=True, timeout=10)
                    if resp.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        logger.info(f"[MediaDownloadQueue] Downloaded cover for {note_id}")
                        return f"/api/media/{filename}"
                    elif resp.status_code == 403:
                        logger.warning(f"[MediaDownloadQueue] Cover 403 for {note_id}, attempt {attempt+1}")
                        time.sleep(0.5)
                except Exception as dl_err:
                    logger.warning(f"[MediaDownloadQueue] Cover attempt {attempt+1} failed: {dl_err}")
                    time.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"[MediaDownloadQueue] Cover error for {note_id}: {e}")
        return None
    
    def _do_download_all_media(self, note_id, note_data):
        """Actual media download implementation (runs in worker thread)"""
        try:
            Config.init_paths()
            note_dir = os.path.join(Config.MEDIA_PATH, str(note_id))
            if not os.path.exists(note_dir):
                os.makedirs(note_dir)
            
            headers = get_common_headers()
            session_pool = get_request_session_pool()
            downloaded_count = 0
            
            # Download images
            if note_data.get('image_list'):
                for idx, img_url in enumerate(note_data['image_list']):
                    ext = '.jpg'
                    filename = f"image_{idx}{ext}"
                    filepath = os.path.join(note_dir, filename)
                    
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                        continue
                    
                    # Build fallback URLs
                    urls_to_try = [img_url]
                    if 'sns-img-qc.xhscdn.com' in img_url or 'sns-img-hw.xhscdn.com' in img_url:
                        img_id = img_url.split('/')[-1].split('?')[0]
                        urls_to_try.extend([
                            f'https://ci.xiaohongshu.com/{img_id}?imageView2/2/w/format/jpg',
                            f'https://sns-img-hw.xhscdn.com/{img_id}?imageView2/2/w/format/jpg',
                        ])
                    elif 'ci.xiaohongshu.com' in img_url and '?' not in img_url:
                        urls_to_try.append(f'{img_url}?imageView2/2/w/format/jpg')
                    
                    for try_url in urls_to_try:
                        try:
                            resp = session_pool.get(try_url, headers=headers, stream=True, timeout=15)
                            if resp.status_code == 200 and int(resp.headers.get('content-length', 0)) > 1024:
                                with open(filepath, 'wb') as f:
                                    for chunk in resp.iter_content(8192):
                                        f.write(chunk)
                                downloaded_count += 1
                                break
                        except Exception:
                            continue
            
            if downloaded_count > 0:
                logger.info(f"[MediaDownloadQueue] Archived {downloaded_count} files for note {note_id}")
                
        except Exception as e:
            logger.error(f"[MediaDownloadQueue] Media error for {note_id}: {e}")


# Global media download queue instance
_media_download_queue = None

def get_media_download_queue():
    """Get the global media download queue instance"""
    global _media_download_queue
    if _media_download_queue is None:
        _media_download_queue = MediaDownloadQueue()
    return _media_download_queue


class SyncService:
    """同步服务类"""
    
    _stop_event = threading.Event()
    _current_sync_mode = 'fast'  # 当前同步模式: 'fast'=极速同步, 'deep'=深度同步
    _rate_limit_counter = 0  # 限流计数器
    _rate_limit_lock = threading.Lock()  # 线程锁
    
    # 心跳超时时间（秒）- 超过此时间没有心跳的任务视为僵死
    HEARTBEAT_TIMEOUT = 300  # 5分钟
    
    @staticmethod
    def _update_heartbeat(account_id):
        """更新账号的同步心跳时间"""
        try:
            Account.query.filter_by(id=account_id).update(
                {'sync_heartbeat': datetime.utcnow()},
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"更新心跳失败 (account_id={account_id}): {e}")
            db.session.rollback()
    
    @staticmethod
    def cleanup_stale_tasks(timeout_seconds=None):
        """清理僵死的同步任务
        
        检测长时间处于 processing 状态但没有心跳更新的任务，将其标记为失败。
        这通常发生在：
        1. 容器重启后，之前的同步线程已终止
        2. 同步线程因致命错误崩溃
        3. 磁盘满、内存不足等系统级错误
        
        Args:
            timeout_seconds: 心跳超时时间（秒），默认使用 HEARTBEAT_TIMEOUT
            
        Returns:
            int: 清理的任务数量
        """
        if timeout_seconds is None:
            timeout_seconds = SyncService.HEARTBEAT_TIMEOUT
            
        try:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
            
            # 查找僵死任务：
            # 1. 状态为 processing
            # 2. 心跳时间为空（旧任务）或心跳超时
            stale_accounts = Account.query.filter(
                Account.status == 'processing',
                db.or_(
                    Account.sync_heartbeat.is_(None),
                    Account.sync_heartbeat < cutoff_time
                )
            ).all()
            
            cleaned_count = 0
            for account in stale_accounts:
                heartbeat_info = ""
                if account.sync_heartbeat:
                    age = (datetime.utcnow() - account.sync_heartbeat).total_seconds()
                    heartbeat_info = f"，最后心跳: {int(age)}秒前"
                else:
                    heartbeat_info = "，无心跳记录"
                
                logger.warning(
                    f"[僵死任务清理] 账号 {account.name or account.user_id} (id={account.id}) "
                    f"状态异常{heartbeat_info}，标记为失败"
                )
                
                account.status = 'failed'
                account.error_message = f"同步任务异常终止（心跳超时），请重新开始同步"
                account.sync_heartbeat = None
                cleaned_count += 1
            
            if cleaned_count > 0:
                db.session.commit()
                logger.info(f"[僵死任务清理] 共清理 {cleaned_count} 个僵死任务")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"[僵死任务清理] 清理失败: {e}")
            db.session.rollback()
            return 0
    
    @staticmethod
    def _reset_rate_limit_counter():
        """重置限流计数器和智能延迟管理器"""
        with SyncService._rate_limit_lock:
            SyncService._rate_limit_counter = 0
        # Reset adaptive delay manager
        get_adaptive_delay_manager().reset()
    
    @staticmethod
    def _record_rate_limit():
        """记录一次限流事件，触发指数退避"""
        with SyncService._rate_limit_lock:
            SyncService._rate_limit_counter += 1
            logger.warning(f"[限流计数] 累计限流次数: {SyncService._rate_limit_counter}")
        # Notify adaptive delay manager for exponential backoff
        get_adaptive_delay_manager().record_rate_limit()
    
    @staticmethod
    def _record_success():
        """记录一次成功请求，触发快速恢复"""
        with SyncService._rate_limit_lock:
            if SyncService._rate_limit_counter > 0:
                SyncService._rate_limit_counter = max(0, SyncService._rate_limit_counter - 1)
        # Notify adaptive delay manager for fast recovery
        get_adaptive_delay_manager().record_success()
    
    @staticmethod
    def _mark_accounts_failed(account_ids, message):
        """将指定账号标记为失败，避免前端一直显示'准备中'"""
        if not account_ids:
            return
        try:
            Account.query.filter(Account.id.in_(list(account_ids))).update(
                {
                    'status': 'failed',
                    'error_message': message,
                    'progress': 0
                },
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"批量标记账号失败: {e}")
            db.session.rollback()
    
    @staticmethod
    def stop_sync():
        """停止同步任务"""
        logger.info("正在停止同步任务...")
        SyncService._stop_event.set()

    @staticmethod
    def _is_media_missing(note):
        """检查笔记的媒体资源是否缺失"""
        if not note:
            return True
            
        try:
            # 1. 检查封面
            if not note.cover_local:
                return True
            cover_path = os.path.join(Config.MEDIA_PATH, os.path.basename(note.cover_local))
            if not os.path.exists(cover_path) or os.path.getsize(cover_path) < 1024:
                return True
                
            # 2. 检查图集/视频目录
            note_dir = os.path.join(Config.MEDIA_PATH, str(note.note_id))
            if not os.path.exists(note_dir):
                # 如果没有目录，肯定缺失
                return True
                
            # 如果是图集，检查是否有图片
            if note.type in ['图集', 'normal']:
                try:
                    img_list = json.loads(note.image_list) if note.image_list else []
                    if len(img_list) > 0:
                        # 简单检查：目录下文件数量是否匹配（或至少有文件）
                        # 严格检查太耗时，这里只要目录下有jpg文件就算有
                        files = [f for f in os.listdir(note_dir) if f.endswith('.jpg') and os.path.getsize(os.path.join(note_dir, f)) > 1024]
                        if len(files) == 0:
                            return True
                except:
                    pass
            
            # 视频类型笔记：不再检查视频文件是否存在（已禁用视频下载，节省磁盘空间）
            # 只要有封面图就认为媒体完整
            # if note.type == '视频':
            #     video_path = os.path.join(note_dir, 'video.mp4')
            #     if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
            #         return True
                    
        except Exception as e:
            logger.warning(f"Error checking media for note {note.note_id}: {e}")
            return True
            
        return False

    @staticmethod
    def _get_missing_required_fields(note):
        """返回笔记缺失的必备字段列表（包括本地资源）"""
        if not note:
            return ['note']

        missing_fields = []

        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')

        # 基础字段(不能为空字符串)
        for field in ['note_id', 'user_id', 'nickname', 'avatar', 'title']:
            if is_blank(getattr(note, field, None)):
                missing_fields.append(field)

        # 描述字段允许空字符串，但不允许为 None
        if getattr(note, 'desc', None) is None:
            missing_fields.append('desc')

        if is_blank(getattr(note, 'upload_time', None)):
            missing_fields.append('upload_time')

        for field in ['cover_remote', 'cover_local']:
            if is_blank(getattr(note, field, None)):
                missing_fields.append(field)

        note_type = getattr(note, 'type', '')
        if note_type == '视频':
            if is_blank(getattr(note, 'video_addr', None)):
                missing_fields.append('video_addr')
        else:
            try:
                image_list = json.loads(note.image_list) if note.image_list else []
            except Exception:
                image_list = []
            # 图集至少要有封面 + 额外图片（>1）
            if len(image_list) <= 1:
                missing_fields.append('image_list')

        if SyncService._is_media_missing(note):
            missing_fields.append('local_media')

        return missing_fields

    @staticmethod
    def _handle_auth_error(msg):
        """检查错误信息是否为认证错误,如果是则标记Cookie失效"""
        auth_errors = ['未登录', '登录已过期', '需要登录', '401', '403', 'Unauthorized', '凭据不合法', '凭据无效', '10062']
        if any(error in str(msg) for error in auth_errors):
            logger.warning(f"检测到认证错误: {msg},正在标记Cookie失效...")
            try:
                # 重新查询当前激活的 cookie
                cookie = Cookie.query.filter_by(is_active=True).first()
                if cookie:
                    cookie.stop_run_timer()
                    cookie.is_valid = False
                    cookie.last_checked = datetime.utcnow()
                    db.session.commit()
                    logger.info("Cookie 已标记为失效")
                return True
            except Exception as e:
                logger.error(f"标记Cookie失效时出错: {e}")
        return False

    @staticmethod
    def _is_xsec_token_error(msg):
        """判断是否为 xsec_token 失效/签名错误"""
        if not msg:
            return False
        tokens = ['xsec', '签名', 'token', '参数错误', 'invalid signature']
        msg_lower = str(msg).lower()
        return any(keyword in msg_lower for keyword in tokens)

    @staticmethod
    def _fetch_user_xsec_token(user_id, xhs_apis, cookie_str):
        """动态获取用户的 xsec_token（不保存到数据库）
        
        用户级别的 xsec_token 用于调用 get_user_all_notes API。
        笔记级别的 xsec_token 从 all_note_info 返回数据中获取。
        
        实现方式：通过搜索用户昵称来获取带 xsec_token 的用户数据。
        """
        if not user_id:
            return ''
        try:
            # 步骤1：先获取用户信息，获取昵称用于搜索
            success_info, msg_info, user_info = xhs_apis.get_user_info(user_id, cookie_str)
            if not success_info or not user_info:
                logger.info(f"Failed to get user info for {user_id}: {msg_info}")
                return ''
            
            # 从返回的用户信息中提取昵称
            basic_info = user_info.get('data', {}).get('basic_info', {})
            nickname = basic_info.get('nickname', '')
            
            if not nickname:
                logger.info(f"No nickname found for user {user_id}")
                return ''
            
            # 步骤2：使用昵称搜索用户，获取包含 xsec_token 的结果
            success_search, msg_search, search_res = xhs_apis.search_user(nickname, cookie_str, page=1)
            if not success_search or not search_res:
                logger.info(f"Failed to search user '{nickname}': {msg_search}")
                return ''
            
            # 步骤3：从搜索结果中匹配 user_id，获取 xsec_token
            users = search_res.get('data', {}).get('users', [])
            for user in users:
                # 检查多种可能的 user_id 字段名
                found_user_id = (user.get('user_id') or 
                                user.get('id') or 
                                user.get('userid') or 
                                user.get('userId'))
                if found_user_id == user_id:
                    xsec_token = user.get('xsec_token', '')
                    if xsec_token:
                        logger.info(f"Fetched xsec_token for user {user_id} via search")
                        return xsec_token
                    else:
                        logger.info(f"User {user_id} found in search but no xsec_token")
                        return ''
            
            logger.info(f"User {user_id} not found in search results for '{nickname}'")
        except Exception as e:
            logger.info(f"Exception fetching xsec_token for user {user_id}: {e}")
        return ''

    @staticmethod
    def _sleep_with_jitter(sync_mode):
        """深度同步时使用智能延迟策略
        
        【重要】深度同步需要请求详情页API，小红书对此有严格的频率限制。
        现在使用 AdaptiveDelayManager 实现智能延迟：
        - 指数退避：限流时自动增加延迟
        - 快速恢复：连续成功时自动减少延迟
        """
        if sync_mode != 'deep':
            return
        
        delay_manager = get_adaptive_delay_manager()
        delay = delay_manager.get_delay()
        
        # Extra random pause to avoid detection (15% probability)
        if random.random() < 0.15:
            delay += random.uniform(5.0, 20.0)
        
        logger.debug(f"[AdaptiveDelay] Sleeping for {delay:.1f}s")
        time.sleep(delay)

    @staticmethod
    def get_cookie_str():
        """获取有效的Cookie字符串（已解密）"""
        cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
        if cookie:
            # 使用新的解密方法
            return cookie.get_cookie_str()
        
        # 从配置获取
        from ..config import Config
        return getattr(Config, 'XHS_COOKIES', '')
    
    @staticmethod
    def start_sync(account_ids, sync_mode='fast'):
        """启动后台同步任务"""
        from .. import create_app
        app = create_app()
        
        # 重置停止标志
        SyncService._stop_event.clear()
        # 记录当前同步模式
        SyncService._current_sync_mode = sync_mode
        
        thread = threading.Thread(target=SyncService._run_sync, args=(app, account_ids, sync_mode))
        thread.daemon = True
        thread.start()
        
        logger.info(f"同步任务已启动: {len(account_ids)} 个账号, 模式: {sync_mode}")
    
    @staticmethod
    def _run_sync(app, account_ids, sync_mode):
        """在后台线程中执行同步
        
        【重要】顶层异常处理：确保任何致命错误（如磁盘满、内存不足）都能被捕获，
        并正确更新数据库状态，避免账号永远停留在 processing 状态。
        """
        with app.app_context():
            try:
                SyncService._sync_accounts(account_ids, sync_mode)
            except Exception as e:
                # 顶层异常捕获：处理任何未被内部捕获的致命错误
                logger.error(f"[致命错误] 同步线程崩溃: {e}")
                try:
                    # 将所有 processing 状态的账号标记为失败
                    error_msg = f"同步线程崩溃: {str(e)[:200]}"
                    affected = Account.query.filter(
                        Account.id.in_(account_ids),
                        Account.status == 'processing'
                    ).update(
                        {
                            'status': 'failed',
                            'error_message': error_msg,
                            'sync_heartbeat': None
                        },
                        synchronize_session=False
                    )
                    db.session.commit()
                    logger.info(f"[致命错误恢复] 已将 {affected} 个账号标记为失败")
                except Exception as inner_e:
                    logger.error(f"[致命错误恢复失败] 无法更新账号状态: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _sync_accounts(account_ids, sync_mode):
        """同步账号的笔记数据"""
        logger.info(f"开始同步账号: {account_ids}, 模式: {sync_mode}")
        
        # 【关键】重置限流计数器，开始新的同步任务
        SyncService._reset_rate_limit_counter()
        logger.info(f"[限流计数] 重置限流计数器")
        
        remaining_ids = set(account_ids)
        cookie_str = SyncService.get_cookie_str()
        if not cookie_str:
            logger.error("未找到有效的 Cookie")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': '未找到有效的Cookie,请先登录小红书'},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        try:
            from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
            from Spider_XHS.xhs_utils.data_util import handle_note_info
            xhs_apis = XHS_Apis()
            # 创建 Data_Spider 实例，用于采集笔记
            data_spider = Data_Spider()
        except Exception as e:
            error_msg = f"初始化API失败: {e}"
            logger.error(f"初始化XHS APIs失败: {e}")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': error_msg},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        # 为每个账号创建日志收集器（仅深度同步模式）
        sync_log_collectors = {}
        
        for acc_id in account_ids:
            # 检查是否停止
            if SyncService._stop_event.is_set():
                logger.info("同步已被用户停止")
                break
                
            # 创建日志收集器（仅深度同步）
            sync_log = None
            if sync_mode == 'deep':
                sync_log = SyncLogCollector(acc_id, sync_mode)
                sync_log_collectors[acc_id] = sync_log
            
            try:
                account = Account.query.get(acc_id)
                if not account:
                    continue
                
                # 当前账号即将处理，移出剩余集合
                remaining_ids.discard(acc_id)
                auth_error_msg = None
                account_name = account.name or account.user_id
                
                # 广播开始同步
                sync_log_broadcaster.info(
                    f"开始同步账号: {account_name}",
                    account_id=acc_id,
                    account_name=account_name
                )
                
                # 更新状态为处理中,清除之前的错误信息和旧日志
                account.status = 'processing'
                account.progress = 0
                # 在开始同步时立即重置已采集数，避免前端轮询时显示旧数据
                account.loaded_msgs = 0
                account.error_message = None
                # 【心跳机制】设置初始心跳时间
                account.sync_heartbeat = datetime.utcnow()
                # 清空旧的同步日志
                if sync_mode == 'deep':
                    account.sync_logs = None
                db.session.commit()
                
                # 构建用户URL,包含xsec_token用于API验证
                # 【重要】用户级别的 xsec_token 每次同步时动态获取，不再保存到数据库
                warning_msg = None
                xsec_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                
                if xsec_token:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                else:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}'
                    warning_msg = f"无法获取用户xsec_token,可能导致同步失败"
                    logger.info(f"Warning: Failed to fetch xsec_token for account {account.user_id}, sync may fail")
                    sync_log_broadcaster.warn(f"无法获取用户 xsec_token，可能导致同步失败", account_id=acc_id, account_name=account_name)
                    if sync_mode == 'deep':
                        error_msg = "深度同步需要有效的 xsec_token，请尝试重新登录后再试"
                        sync_log_broadcaster.error(error_msg, account_id=acc_id, account_name=account_name)
                        account.status = 'failed'
                        account.error_message = error_msg
                        db.session.commit()
                        continue
                
                # 获取用户所有笔记列表
                success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                # 如果失败且是token错误，尝试重新获取token并重试
                if not success and sync_mode == 'deep' and SyncService._is_xsec_token_error(msg):
                    new_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                    if new_token and new_token != xsec_token:
                        xsec_token = new_token
                        user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                        success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                # 策略优化:如果获取成功但列表为空,尝试重新获取xsec_token并重试一次
                if success and not all_note_info:
                    logger.info(f"Got 0 notes for {account.user_id}, attempting to refresh xsec_token and retry...")
                    new_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                    if new_token and new_token != xsec_token:
                        logger.info(f"Got new xsec_token: {new_token[:10]}...")
                        xsec_token = new_token
                        user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                        success_retry, msg_retry, all_note_info_retry = xhs_apis.get_user_all_notes(user_url, cookie_str)
                        
                        if success_retry and all_note_info_retry:
                            logger.info(f"Retry success! Got {len(all_note_info_retry)} notes.")
                            success = success_retry
                            msg = msg_retry
                            all_note_info = all_note_info_retry
                        else:
                            logger.info(f"Retry result: success={success_retry}, count={len(all_note_info_retry) if all_note_info_retry else 0}")

                if not success:
                    # 检查是否为认证错误
                    if SyncService._handle_auth_error(msg):
                        error_msg = f"Cookie已失效,请重新登录。原始错误: {msg}"
                        auth_error_msg = error_msg
                        # 标记停止,不再尝试后续账号
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, error_msg)
                    else:
                        error_msg = f"获取笔记列表失败: {msg}"

                    if warning_msg:
                        error_msg = f"{warning_msg}。{error_msg}"
                    logger.info(f"Failed to get notes for {account.user_id}: {msg}")
                    account.status = 'failed'
                    account.error_message = error_msg
                    db.session.commit()
                    if auth_error_msg:
                        break
                    continue
                
                # 【关键修复】如果API成功但返回空列表,标记为失败而不是继续
                if success and not all_note_info:
                    error_msg = "获取笔记列表为空,可能是xsec_token失效或该用户没有公开笔记"
                    if warning_msg:
                        error_msg = f"{warning_msg}。{error_msg}"
                    logger.info(f"Empty notes for {account.user_id} after all retries")
                    account.status = 'failed'
                    account.error_message = error_msg
                    account.total_msgs = 0
                    account.loaded_msgs = 0
                    account.progress = 0
                    db.session.commit()
                    continue

                # 尝试获取并更新用户信息（头像、昵称、粉丝数等）
                try:
                    success_info, msg_info, user_info_res = xhs_apis.get_user_info(account.user_id, cookie_str)
                    
                    if not success_info and SyncService._handle_auth_error(msg_info):
                        auth_error_msg = f"Cookie已失效,同步终止。错误: {msg_info}"
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                    
                    if success_info and user_info_res and user_info_res.get('data'):
                        user_data = user_info_res['data']
                        if user_data:
                            account.name = user_data.get('basic_info', {}).get('nickname') or account.name
                            account.avatar = user_data.get('basic_info', {}).get('images') or account.avatar
                            account.desc = user_data.get('basic_info', {}).get('desc') or account.desc
                            
                            # 更新互动数据
                            interactions = user_data.get('interactions', [])
                            for interaction in interactions:
                                if interaction.get('type') == 'fans':
                                    account.fans = interaction.get('count')
                                elif interaction.get('type') == 'follows':
                                    account.follows = interaction.get('count')
                                elif interaction.get('type') == 'interaction':
                                    account.interaction = interaction.get('count')
                            
                            db.session.commit()
                            logger.info(f"Updated user info for {account.user_id}: fans={account.fans}")
                except Exception as e:
                    logger.info(f"Failed to update user info for {account.user_id}: {e}")
                
                total = len(all_note_info)
                account.total_msgs = total
                # 不再重置loaded_msgs为0,而是保留之前的值,或者根据实际情况更新
                # 如果是全新的同步开始,可能需要重置,但如果是增量或者状态更新,这会让人困惑
                # 现在的逻辑是:每次同步都是从头遍历所有笔记,所以重置为0是合理的
                # 但如果total > 0且最终success,loaded_msgs应该等于total
                account.loaded_msgs = 0 
                db.session.commit()
                
                # 广播获取笔记列表成功
                sync_log_broadcaster.info(
                    f"获取笔记列表成功，共 {total} 篇笔记",
                    account_id=acc_id,
                    account_name=account_name,
                    extra={'total': total}
                )
                
                # 设置日志收集器的总数
                if sync_log:
                    sync_log.set_total(total)
                
                # 【性能优化】预加载已存在的笔记ID和需要更新的笔记到内存缓存
                # 避免每次循环都查询数据库，大幅减少数据库查询次数
                all_note_ids = [n.get('note_id') or n.get('id') for n in all_note_info]
                existing_notes_query = Note.query.filter(Note.note_id.in_(all_note_ids)).all()
                existing_notes_cache = {n.note_id: n for n in existing_notes_query}
                existing_note_ids_cache = set(existing_notes_cache.keys())
                logger.info(f"[内存缓存] 预加载 {len(existing_note_ids_cache)}/{len(all_note_ids)} 条已存在笔记")
                
                # 处理每个笔记
                # 【重要】笔记级别的xsec_token应从get_user_all_notes返回的all_note_info中获取
                # 参考main.py: note_url = f"https://www.xiaohongshu.com/explore/{simple_note_info['note_id']}?xsec_token={simple_note_info['xsec_token']}"
                
                # 【性能优化】极速同步模式下使用批量保存
                FAST_SYNC_BATCH_SIZE = 20  # batch size for bulk operations in fast sync mode
                fast_sync_batch = []  # batch buffer for fast sync mode
                
                for idx, simple_note in enumerate(all_note_info):
                    # 检查是否停止
                    if SyncService._stop_event.is_set():
                        print("Sync stopped by user during note processing")
                        break

                    # 【关键修复】兼容API返回的两种字段名:'note_id'和'id'
                    note_id = simple_note.get('note_id') or simple_note.get('id')
                    # 【关键】笔记的xsec_token从all_note_info返回数据中获取，不使用账号级别的token作为后备
                    note_xsec_token = simple_note.get('xsec_token', '')
                    if note_xsec_token:
                        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_xsec_token}&xsec_source=pc_search"
                    else:
                        # 如果笔记没有xsec_token，记录警告
                        logger.warning(f"Note {note_id} missing xsec_token from all_note_info")
                        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                    
                    need_fetch_detail = False
                    
                    if sync_mode == 'deep':
                        # 方案B:深度同步(增量模式)
                        # 【性能优化】使用内存缓存检查笔记是否存在，避免每次查询数据库
                        existing_note = existing_notes_cache.get(note_id)
                        
                        missing_fields = []
                        if not existing_note:
                            need_fetch_detail = True
                            missing_fields = ['new_note']
                            logger.info(f"Note {note_id} not exists, will fetch detail")
                        else:
                            missing_fields = SyncService._get_missing_required_fields(existing_note)
                            if missing_fields:
                                need_fetch_detail = True
                                logger.info(
                                    f"Note {note_id} missing required fields {missing_fields}, will fetch detail"
                                )
                    else:
                        # 方案A:极速同步
                        # 永远只使用列表页数据,不获取详情
                        need_fetch_detail = False

                    if not need_fetch_detail:
                        # 极速更新(只更新互动数据)
                        # 【重要说明】列表页API只返回点赞数,不返回收藏、评论、转发数和发布时间
                        try:
                            # 从列表页数据中提取互动信息，传入笔记级别的xsec_token
                            cleaned_data = handle_note_info(simple_note, from_list=True, xsec_token=note_xsec_token)
                            
                            if sync_mode == 'deep':
                                # 深度模式下,如果是旧笔记,只更新点赞数（列表页唯一可用的互动数据）
                                # 【性能优化】使用内存缓存获取笔记对象，避免重复查询数据库
                                existing_note = existing_notes_cache.get(note_id)
                                if existing_note:
                                    # 只更新点赞数,其他数据保留（因为列表页不提供）
                                    if cleaned_data['liked_count'] is not None:
                                        existing_note.liked_count = cleaned_data['liked_count']
                                    existing_note.last_updated = datetime.utcnow()
                                    # 【性能优化】不立即提交，由主循环统一批量提交
                                    # 记录跳过（已有完整数据）
                                    if sync_log:
                                        sync_log.record_skipped()
                            else:
                                # 【性能优化】极速模式下，收集到批量缓冲区，延迟批量保存
                                fast_sync_batch.append(cleaned_data)
                                
                                # 每 FAST_SYNC_BATCH_SIZE 条批量保存一次
                                if len(fast_sync_batch) >= FAST_SYNC_BATCH_SIZE:
                                    try:
                                        # 【性能优化】传入预加载的缓存，避免重复查询
                                        inserted, updated = SyncService._bulk_save_notes(
                                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                                        )
                                        logger.info(f"[极速同步] 批量保存 {len(fast_sync_batch)} 条: 插入 {inserted}, 更新 {updated}")
                                    except Exception as e:
                                        logger.error(f"[极速同步] 批量保存失败: {e}")
                                    fast_sync_batch = []  # clear batch buffer
                                
                        except Exception as e:
                            logger.info(f"Error quick updating note {note_id}: {e}")
                    else:
                        # 需要获取详情(深度模式下的新笔记或缺失素材笔记)
                        detail_saved = False
                        rate_limited = False
                        last_error_msg = None
                        
                        # 带重试的详情获取
                        for retry_attempt in range(3):
                            if retry_attempt > 0:
                                # 重试前等待更长时间
                                wait_time = random.uniform(3, 6) * retry_attempt
                                logger.info(f"Retrying note {note_id} after {wait_time:.1f}s (attempt {retry_attempt + 1}/3)")
                                time.sleep(wait_time)
                            
                            # 使用 Data_Spider 采集笔记详情（内部已调用 handle_note_info）
                            success, msg, note_info = data_spider.spider_note(note_url, cookie_str)
                            last_error_msg = msg
                            
                            # 检查是否被限流或笔记不可用
                            is_rate_limited = '频次异常' in str(msg) or '频繁操作' in str(msg)
                            is_unavailable = '暂时无法浏览' in str(msg) or '笔记不存在' in str(msg)
                            
                            if is_rate_limited:
                                rate_limited = True
                                logger.warning(f"Rate limited for note {note_id}: {msg}")
                                # 【关键】记录限流事件，触发动态退避
                                SyncService._record_rate_limit()
                                # 广播限流警告
                                sync_log_broadcaster.warn(
                                    f"访问频次异常，正在重试 ({retry_attempt + 1}/3)",
                                    account_id=acc_id,
                                    account_name=account_name,
                                    note_id=note_id
                                )
                                # 记录限流日志
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_RATE_LIMITED,
                                        note_id=note_id,
                                        message=str(msg),
                                        extra={'retry': retry_attempt + 1, 'rate_limit_count': SyncService._rate_limit_counter}
                                    )
                                # 【智能延迟】使用自适应延迟管理器计算等待时间
                                wait_time = get_adaptive_delay_manager().get_rate_limit_wait()
                                logger.info(f"[限流重试] 智能等待 {wait_time:.1f}s 后重试")
                                time.sleep(wait_time)
                                continue  # 重试
                            
                            if is_unavailable:
                                logger.warning(f"Note {note_id} unavailable: {msg}")
                                sync_log_broadcaster.warn(
                                    f"笔记暂时无法浏览: {msg}",
                                    account_id=acc_id,
                                    account_name=account_name,
                                    note_id=note_id
                                )
                                # 记录笔记不可用日志
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_UNAVAILABLE,
                                        note_id=note_id,
                                        message=str(msg)
                                    )
                                break  # 不重试，笔记本身有问题
                            
                            if not success:
                                # 检查认证错误
                                if SyncService._handle_auth_error(msg):
                                    logger.info(f"Auth error during note detail fetch: {msg}")
                                    auth_error_msg = f"Cookie已失效,同步终止。错误: {msg}"
                                    sync_log_broadcaster.error(
                                        f"Cookie 已失效，同步终止: {msg}",
                                        account_id=acc_id,
                                        account_name=account_name,
                                        note_id=note_id
                                    )
                                    # 记录认证错误日志
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_AUTH_ERROR,
                                            note_id=note_id,
                                            message=str(msg)
                                        )
                                        sync_log.save_to_db()
                                    SyncService.stop_sync()
                                    account.status = 'failed'
                                    account.error_message = auth_error_msg
                                    db.session.commit()
                                    SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                                    break
                                elif SyncService._is_xsec_token_error(msg):
                                    # 【重要】笔记的xsec_token来自get_user_all_notes返回数据，失效时不应尝试刷新账号token
                                    # 参考main.py: 笔记token应从all_note_info中获取
                                    sync_log_broadcaster.warn(
                                        f"笔记 xsec_token 失效，跳过该笔记",
                                        account_id=acc_id,
                                        account_name=account_name,
                                        note_id=note_id
                                    )
                                    # 记录Token失效日志
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_TOKEN_REFRESH,
                                            note_id=note_id,
                                            message=f"笔记xsec_token失效（来自all_note_info）: {msg}"
                                        )
                                    logger.warning(f"Note {note_id} xsec_token invalid, skipping: {msg}")
                                    break  # 跳出重试循环，继续处理下一个笔记
                                else:
                                    # 非认证错误，记录日志
                                    logger.warning(f"Failed to get note detail for {note_id}: {msg}")
                                    sync_log_broadcaster.error(
                                        f"获取笔记详情失败: {msg}",
                                        account_id=acc_id,
                                        account_name=account_name,
                                        note_id=note_id
                                    )
                                    # 记录获取失败日志
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_FETCH_FAILED,
                                            note_id=note_id,
                                            message=str(msg)
                                        )
                                    break

                            # spider_note 返回的 note_info 已经是处理过的数据
                            if success and note_info:
                                try:
                                    # 补充 xsec_token 字段（spider_note 内部的 handle_note_info 没有传递此参数）
                                    note_info['xsec_token'] = note_xsec_token
                                    
                                    # 【调试日志】打印清洗后的关键字段
                                    logger.info(f"[深度同步调试] note_id={note_id}, note_info: upload_time={note_info.get('upload_time')}, collected_count={note_info.get('collected_count')}, comment_count={note_info.get('comment_count')}")
                                    
                                    # 深度同步获取详情后，下载所有媒体资源
                                    # 【性能优化】auto_commit=False，由主循环统一批量提交，减少 SQLite 锁竞争
                                    SyncService._save_note(note_info, download_media=True, auto_commit=False)
                                    detail_saved = True
                                    # 【关键】记录成功，减少限流计数
                                    SyncService._record_success()
                                    # 记录成功
                                    if sync_log:
                                        sync_log.record_success()
                                    logger.info(f"[深度同步] 笔记 {note_id} 详情获取成功，含发布时间: {note_info.get('upload_time', '未知')}")
                                    break  # 成功，跳出重试循环
                                except Exception as e:
                                    logger.warning(f"Error saving note {note_id}: {e}")
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_FETCH_FAILED,
                                            note_id=note_id,
                                            message=f"保存错误: {str(e)}"
                                        )
                                    break
                            else:
                                # API 返回 success=True 但数据为空，可能是限流或 token 问题
                                logger.warning(f"Note {note_id} has no valid data in response: {msg}")
                                if '频次' in str(msg) or '频繁' in str(msg):
                                    rate_limited = True
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_RATE_LIMITED,
                                            note_id=note_id,
                                            message=f"API返回空数据: {msg}"
                                        )
                                    continue  # 重试
                                break  # 其他原因，不重试
                        
                        # 如果因为限流导致3次都失败，增加额外等待（从配置读取）
                        if rate_limited and not detail_saved:
                            # 【智能延迟】使用自适应延迟管理器计算等待时间
                            total_wait = get_adaptive_delay_manager().get_rate_limit_wait() * 1.5
                            logger.warning(f"[限流失败] 笔记 {note_id} 连续限流，智能等待 {total_wait:.1f}s 后继续")
                            time.sleep(total_wait)
                        
                        # 【关键修复】如果详情获取失败，至少保存列表页的基本数据
                        # 这样封面等信息能从列表页获取，不会完全为空
                        if not detail_saved:
                            # 【重要警告】详情获取失败意味着该笔记将缺少：发布时间、收藏数、评论数、转发数
                            logger.warning(f"[深度同步] 笔记 {note_id} 详情获取失败，将缺少发布时间等字段！原因: {'限流' if rate_limited else '其他'}")
                            
                            # 记录字段缺失日志
                            if sync_log:
                                sync_log.add_issue(
                                    SyncLogCollector.TYPE_MISSING_FIELD,
                                    note_id=note_id,
                                    message=f"详情获取失败，回退到列表页数据，缺失字段: upload_time, collected_count, comment_count, share_count",
                                    fields=['upload_time', 'collected_count', 'comment_count', 'share_count'],
                                    extra={'reason': '限流' if rate_limited else '获取失败', 'original_error': str(last_error_msg)[:200]}
                                )
                            
                            try:
                                logger.info(f"Saving note {note_id} with list data as fallback (无发布时间)")
                                # 传入笔记级别的xsec_token以便存储
                                cleaned_data = handle_note_info(simple_note, from_list=True, xsec_token=note_xsec_token)
                                # 列表页数据，不下载完整媒体（因为没有详情），但封面可以获取
                                # 【性能优化】auto_commit=False，由主循环统一批量提交，减少 SQLite 锁竞争
                                SyncService._save_note(cleaned_data, download_media=False, auto_commit=False)
                            except Exception as e:
                                logger.warning(f"Error saving note {note_id} with list data: {e}")
                        
                        # 请求间隔,避免被封（仅在请求详情页时等待,加入随机抖动）
                        SyncService._sleep_with_jitter(sync_mode)
                    
                    # 更新进度
                    # 只有在确实处理了笔记时才更新loaded_msgs?
                    # 不,我们遍历了列表,所以应该算作已处理（即使是跳过详情获取）
                    # 但为了界面显示准确,如果total为0,progress设为100
                    account.loaded_msgs = idx + 1
                    account.progress = int(((idx + 1) / total) * 100) if total > 0 else 100
                    
                    # 【性能优化】减少数据库写入频率，避免 SQLite 锁阻塞 API 请求
                    # 每处理 5 条笔记或最后一条时才提交，大幅减少锁定时间
                    should_commit = (idx + 1) % 5 == 0 or idx == total - 1
                    if should_commit:
                        # 【心跳机制】同时更新心跳时间，表明任务仍在运行
                        account.sync_heartbeat = datetime.utcnow()
                        db.session.commit()
                        
                        # 【WebSocket 推送】实时广播进度到前端
                        sync_log_broadcaster.broadcast_progress(
                            account_id=acc_id,
                            status='processing',
                            progress=account.progress,
                            loaded_msgs=account.loaded_msgs,
                            total_msgs=total
                        )
                    
                    # 极速模式下不需要sleep
                    if sync_mode == 'fast':
                        # time.sleep(0.05) 
                        pass
                
                # 【性能优化】保存剩余的批量数据（极速同步模式）
                if sync_mode == 'fast' and fast_sync_batch:
                    try:
                        # 【性能优化】传入预加载的缓存，避免重复查询
                        inserted, updated = SyncService._bulk_save_notes(
                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                        )
                        logger.info(f"[极速同步] 保存剩余 {len(fast_sync_batch)} 条: 插入 {inserted}, 更新 {updated}")
                    except Exception as e:
                        logger.error(f"[极速同步] 保存剩余数据失败: {e}")
                    fast_sync_batch = []
                
                # 完成同步
                if auth_error_msg:
                    # 认证错误时当前账号已标记失败，其余账号也已处理
                    # 保存日志
                    if sync_log:
                        sync_log.save_to_db()
                    break
                if not SyncService._stop_event.is_set():
                    account.status = 'completed'
                    # 确保进度为100%
                    account.progress = 100
                    # 确保loaded_msgs等于total,即使中途有跳过的情况（只要不是报错退出）
                    # 因为我们遍历了所有笔记列表
                    account.loaded_msgs = total
                    account.last_sync = datetime.utcnow()
                    # 【心跳机制】任务完成，清除心跳
                    account.sync_heartbeat = None
                    
                    # 保存同步日志
                    if sync_log:
                        logs_data = sync_log.finalize()
                        account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                        
                        # 如果有问题，生成摘要消息
                        summary = logs_data.get('summary', {})
                        issues_count = summary.get('rate_limited', 0) + summary.get('missing_field', 0) + summary.get('fetch_failed', 0)
                        if issues_count > 0:
                            account.error_message = f"同步完成，但有 {issues_count} 个问题: 限流{summary.get('rate_limited', 0)}次, 字段缺失{summary.get('missing_field', 0)}条, 获取失败{summary.get('fetch_failed', 0)}条"
                            sync_log_broadcaster.warn(
                                f"同步完成，但有 {issues_count} 个问题",
                                account_id=acc_id,
                                account_name=account_name,
                                extra=summary
                            )
                        else:
                            sync_log_broadcaster.info(
                                f"同步完成，共处理 {total} 篇笔记",
                                account_id=acc_id,
                                account_name=account_name
                            )
                        # 【WebSocket 推送】广播同步完成事件
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed', summary)
                    else:
                        # 极速模式完成
                        sync_log_broadcaster.info(
                            f"同步完成，共处理 {total} 篇笔记",
                            account_id=acc_id,
                            account_name=account_name
                        )
                        # 【WebSocket 推送】广播同步完成事件
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed')
                else:
                    # 如果是因为停止而退出循环,且状态仍为processing
                    if account.status == 'processing':
                        account.status = 'failed'
                        mode_name = '深度同步' if sync_mode == 'deep' else '极速同步'
                        account.error_message = account.error_message or f"用户手动停止{mode_name}"
                        # 【心跳机制】任务停止，清除心跳
                        account.sync_heartbeat = None
                        sync_log_broadcaster.warn(
                            f"用户手动停止同步",
                            account_id=acc_id,
                            account_name=account_name
                        )
                        # 【WebSocket 推送】广播停止事件
                        sync_log_broadcaster.broadcast_completed(acc_id, 'cancelled')
                    # 保存日志
                    if sync_log:
                        sync_log.save_to_db()
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error syncing account {acc_id}: {e}")
                sync_log_broadcaster.error(
                    f"同步异常: {str(e)}",
                    account_id=acc_id,
                    account_name=locals().get('account_name')
                )
                # 先回滚session,避免PendingRollbackError
                db.session.rollback()
                try:
                    account = Account.query.get(acc_id)
                    if account:
                        account.status = 'failed'
                        account.error_message = f"同步出错: {str(e)}"
                        # 【心跳机制】异常时清除心跳
                        account.sync_heartbeat = None
                        # 保存同步日志
                        if sync_log:
                            sync_log.add_issue(
                                SyncLogCollector.TYPE_FETCH_FAILED,
                                message=f"同步异常: {str(e)}"
                            )
                            logs_data = sync_log.finalize()
                            account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                        db.session.commit()
                except Exception as inner_e:
                    logger.error(f"Error updating account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _bulk_save_notes(notes_data_list, existing_note_ids=None):
        """批量保存笔记到数据库（使用bulk操作提高性能）
        
        适用于极速同步模式，不下载媒体文件。
        
        Args:
            notes_data_list: 笔记数据字典列表
            existing_note_ids: 已存在的笔记ID集合，用于区分插入和更新
        
        Returns:
            tuple: (inserted_count, updated_count)
        """
        if not notes_data_list:
            return 0, 0
        
        try:
            # Pre-fetch existing note IDs if not provided
            if existing_note_ids is None:
                note_ids = [n.get('note_id') for n in notes_data_list if n.get('note_id')]
                existing_notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
                existing_note_ids = {n.note_id for n in existing_notes}
                existing_notes_map = {n.note_id: n for n in existing_notes}
            else:
                # Query existing notes for update
                note_ids = [n.get('note_id') for n in notes_data_list if n.get('note_id')]
                existing_notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
                existing_notes_map = {n.note_id: n for n in existing_notes}
            
            # Separate into insert and update batches
            insert_mappings = []
            update_count = 0
            now = datetime.utcnow()
            
            # 【性能优化】收集需要异步下载的封面任务
            cover_tasks = []
            
            for note_data in notes_data_list:
                note_id = note_data.get('note_id')
                if not note_id:
                    continue
                
                # Calculate cover remote URL only, download is async
                cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
                if not cover_remote:
                    imgs = note_data.get('image_list') or []
                    cover_remote = imgs[0] if len(imgs) > 0 else None
                
                # 【性能优化】不再同步下载封面，而是收集任务后异步处理
                cover_local = None  # Will be updated by async callback
                
                # Collect cover download task for async processing
                if cover_remote:
                    cover_tasks.append((cover_remote, note_id))
                
                if note_id in existing_note_ids:
                    # Update existing note - update in-place
                    note = existing_notes_map.get(note_id)
                    if note:
                        note.nickname = note_data['nickname']
                        note.avatar = note_data['avatar']
                        note.title = note_data['title']
                        if note_data['desc'] is not None and note_data['desc'] != '':
                            note.desc = note_data['desc']
                        note.type = note_data['note_type']
                        
                        if note_data['liked_count'] is not None:
                            note.liked_count = note_data['liked_count']
                        if note_data['collected_count'] is not None:
                            note.collected_count = note_data['collected_count']
                        if note_data['comment_count'] is not None:
                            note.comment_count = note_data['comment_count']
                        if note_data['share_count'] is not None:
                            note.share_count = note_data['share_count']
                        if note_data['upload_time'] is not None:
                            note.upload_time = note_data['upload_time']
                        if note_data['video_addr']:
                            note.video_addr = note_data['video_addr']
                        if note_data['image_list']:
                            new_img_count = len(note_data['image_list'])
                            try:
                                old_img_list = json.loads(note.image_list) if note.image_list else []
                                old_img_count = len(old_img_list)
                            except:
                                old_img_count = 0
                            if new_img_count > old_img_count or old_img_count <= 1:
                                note.image_list = json.dumps(note_data['image_list'])
                        if note_data['tags']:
                            note.tags = json.dumps(note_data['tags'])
                        if note_data['ip_location']:
                            note.ip_location = note_data['ip_location']
                        if cover_remote:
                            note.cover_remote = cover_remote
                        if cover_local:
                            note.cover_local = cover_local
                        if note_data.get('xsec_token'):
                            note.xsec_token = note_data['xsec_token']
                        note.last_updated = now
                        update_count += 1
                else:
                    # Prepare mapping for bulk insert
                    mapping = {
                        'note_id': note_id,
                        'user_id': note_data['user_id'],
                        'nickname': note_data['nickname'],
                        'avatar': note_data['avatar'],
                        'title': note_data['title'],
                        'desc': note_data['desc'] or '',
                        'type': note_data['note_type'],
                        'liked_count': note_data['liked_count'] if note_data['liked_count'] is not None else 0,
                        'collected_count': note_data['collected_count'] if note_data['collected_count'] is not None else 0,
                        'comment_count': note_data['comment_count'] if note_data['comment_count'] is not None else 0,
                        'share_count': note_data['share_count'] if note_data['share_count'] is not None else 0,
                        'upload_time': note_data['upload_time'] or '',
                        'video_addr': note_data['video_addr'] or '',
                        'image_list': json.dumps(note_data['image_list']) if note_data['image_list'] else '[]',
                        'tags': json.dumps(note_data['tags']) if note_data['tags'] else '[]',
                        'ip_location': note_data['ip_location'] or '',
                        'cover_remote': cover_remote or '',
                        'cover_local': cover_local or '',
                        'xsec_token': note_data.get('xsec_token') or '',
                        'last_updated': now,
                    }
                    insert_mappings.append(mapping)
            
            # Bulk insert new notes
            if insert_mappings:
                db.session.bulk_insert_mappings(Note, insert_mappings)
                logger.info(f"[批量插入] 插入 {len(insert_mappings)} 条新笔记")
            
            # Commit all changes (updates are already tracked by session)
            db.session.commit()
            
            # 【性能优化】提交所有封面下载任务到异步队列
            if cover_tasks:
                queue = get_media_download_queue()
                for cover_url, nid in cover_tasks:
                    queue.submit_cover_download(cover_url, nid, callback=SyncService._update_cover_local)
                logger.info(f"[批量保存] 提交 {len(cover_tasks)} 个封面下载任务到异步队列")
            
            return len(insert_mappings), update_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"[批量保存] 批量保存笔记失败: {e}")
            raise

    # Maximum concurrent image downloads per note
    MAX_CONCURRENT_DOWNLOADS = 5
    
    @staticmethod
    def _download_single_image(note_id, note_dir, idx, img_url, headers):
        """Download a single image with retry logic using session pool.
        
        Args:
            note_id: Note ID for logging
            note_dir: Directory to save the image
            idx: Image index
            img_url: Original image URL
            headers: HTTP headers for request
            
        Returns:
            bool: True if download succeeded, False otherwise
        """
        ext = '.jpg'
        filename = f"image_{idx}{ext}"
        filepath = os.path.join(note_dir, filename)
        
        # Skip if file already exists
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
            logger.info(f"Skipping existing image {idx} for note {note_id}")
            return True
        
        # Build fallback URLs
        urls_to_try = [img_url]
        
        if 'sns-img-qc.xhscdn.com' in img_url or 'sns-img-hw.xhscdn.com' in img_url:
            img_id = img_url.split('/')[-1].split('?')[0]
            urls_to_try.extend([
                f'https://ci.xiaohongshu.com/{img_id}?imageView2/2/w/format/jpg',
                f'https://sns-img-hw.xhscdn.com/{img_id}?imageView2/2/w/format/jpg',
                f'https://sns-img-qc.xhscdn.com/{img_id}?imageView2/2/w/format/jpg',
            ])
        elif 'ci.xiaohongshu.com' in img_url and '?' not in img_url:
            urls_to_try.append(f'{img_url}?imageView2/2/w/format/jpg')
        
        # Use session pool for connection reuse
        session_pool = get_request_session_pool()
        
        # Try each URL
        for try_url in urls_to_try:
            try:
                logger.info(f"Downloading image {idx} from {try_url}")
                resp = session_pool.get(try_url, headers=headers, stream=True, timeout=20)
                if resp.status_code == 200 and int(resp.headers.get('content-length', 0)) > 1024:
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    logger.info(f"Successfully downloaded image {idx}")
                    return True
                else:
                    logger.info(f"URL returned {resp.status_code}, trying next URL...")
            except Exception as e:
                logger.info(f"Failed with {try_url}: {e}")
                continue
        
        logger.warning(f"Failed to download image {idx} for {note_id} after trying all URLs")
        return False
    
    @staticmethod
    def _download_all_media(note_id, note_data):
        """下载笔记的所有媒体资源（图片/视频）到本地归档，使用并行下载加速"""
        try:
            logger.info(f"Starting media download for note {note_id}...")
            # 创建笔记专属目录
            note_dir = os.path.join(Config.MEDIA_PATH, str(note_id))
            if not os.path.exists(note_dir):
                os.makedirs(note_dir)
            
            headers = get_common_headers()
            downloaded_count = 0
            
            # 1. 并行下载图片列表
            if note_data.get('image_list'):
                image_list = note_data['image_list']
                logger.info(f"Downloading {len(image_list)} images for note {note_id} (parallel, max {SyncService.MAX_CONCURRENT_DOWNLOADS} concurrent)")
                
                # Use ThreadPoolExecutor for parallel downloads
                with ThreadPoolExecutor(max_workers=SyncService.MAX_CONCURRENT_DOWNLOADS) as executor:
                    # Submit all download tasks
                    futures = {
                        executor.submit(
                            SyncService._download_single_image,
                            note_id, note_dir, idx, img_url, headers
                        ): idx
                        for idx, img_url in enumerate(image_list)
                    }
                    
                    # Collect results
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            if future.result():
                                downloaded_count += 1
                        except Exception as e:
                            logger.error(f"Error downloading image {idx} for {note_id}: {e}")
            else:
                logger.info(f"No image_list found for note {note_id}")
            
            # 2. 跳过视频下载（节省磁盘空间，只采集封面图）
            # 如果需要下载视频，取消下面的注释
            # if note_data.get('note_type') == '视频' and note_data.get('video_addr'):
            #     video_url = note_data['video_addr']
            #     filename = f"video.mp4"
            #     filepath = os.path.join(note_dir, filename)
            #     
            #     logger.info(f"Downloading video for note {note_id} from {video_url}")
            #     
            #     if not (os.path.exists(filepath) and os.path.getsize(filepath) > 1024):
            #         try:
            #             resp = requests.get(video_url, headers=headers, stream=True, timeout=60)
            #             if resp.status_code == 200:
            #                 with open(filepath, 'wb') as f:
            #                     for chunk in resp.iter_content(1024*1024): # 1MB chunks
            #                         f.write(chunk)
            #                 downloaded_count += 1
            #                 logger.info(f"Successfully downloaded video for {note_id}")
            #             else:
            #                 logger.warning(f"Failed to download video for {note_id}: {resp.status_code}")
            #         except Exception as e:
            #             logger.warning(f"Error downloading video for {note_id}: {e}")
            #     else:
            #         logger.info(f"Skipping existing video for note {note_id}")
            # elif note_data.get('note_type') == '视频':
            #     logger.warning(f"Video note {note_id} missing video_addr")
            if note_data.get('note_type') == '视频':
                logger.info(f"Skipping video download for note {note_id} (video download disabled)")

            if downloaded_count > 0:
                logger.info(f"Archived {downloaded_count} media files for note {note_id}")
            else:
                logger.info(f"No media files downloaded for note {note_id} (maybe already exists or empty list)")
                
        except Exception as e:
            logger.error(f"Error in _download_all_media for {note_id}: {e}")

    @staticmethod
    def _save_note(note_data, download_media=False, auto_commit=True):
        """保存笔记到数据库（使用merge避免重复插入）
        
        【重要说明】
        列表页API只返回部分数据（点赞数）,不返回收藏、评论、转发数和发布时间。
        当这些字段为None时,表示"数据不可用",应保留数据库中的现有值。
        
        Args:
            note_data: 笔记数据字典
            download_media: 是否下载媒体文件
            auto_commit: 是否自动提交，设为False可用于批量操作时由调用者统一提交
        """
        try:
            # 【关键检查】确保note_id不为空
            note_id = note_data.get('note_id')
            if not note_id:
                logger.info(f"Skipping note save: note_id is empty. Data: {note_data.get('title', 'unknown')}")
                return

            # 计算封面（远程URL）
            cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
            if not cover_remote:
                imgs = note_data.get('image_list') or []
                cover_remote = imgs[0] if len(imgs) > 0 else None
            
            # 【性能优化】封面下载改为异步，不阻塞主流程
            # cover_local 初始为 None，后续由异步队列下载完成后更新
            cover_local = None
            
            # 使用merge实现upsert语义,避免唯一约束冲突
            note = Note.query.filter_by(note_id=note_id).first()
            
            if note:
                # 更新现有笔记 - 只更新非None的字段
                note.nickname = note_data['nickname']
                note.avatar = note_data['avatar']
                note.title = note_data['title']
                # desc可能为空字符串,但不应覆盖现有描述（除非详情页明确返回）
                if note_data['desc'] is not None and note_data['desc'] != '':
                    note.desc = note_data['desc']
                note.type = note_data['note_type']
                
                # 【关键逻辑】互动数据:只有非None时才更新
                # liked_count列表页有返回,始终更新
                if note_data['liked_count'] is not None:
                    note.liked_count = note_data['liked_count']
                # collected_count、comment_count、share_count列表页不返回（为None）,保留原值
                if note_data['collected_count'] is not None:
                    note.collected_count = note_data['collected_count']
                if note_data['comment_count'] is not None:
                    note.comment_count = note_data['comment_count']
                if note_data['share_count'] is not None:
                    note.share_count = note_data['share_count']
                
                # 【关键逻辑】发布时间:列表页不返回（为None）,保留原值
                if note_data['upload_time'] is not None:
                    note.upload_time = note_data['upload_time']
                
                # 媒体数据:只有非空时才更新
                if note_data['video_addr']:
                    note.video_addr = note_data['video_addr']
                # 【关键修复】图片列表:只有当新列表数量大于现有数量时才更新
                # 防止列表页的1张封面覆盖详情页的完整图片列表
                if note_data['image_list']:
                    new_img_count = len(note_data['image_list'])
                    try:
                        old_img_list = json.loads(note.image_list) if note.image_list else []
                        old_img_count = len(old_img_list)
                    except:
                        old_img_count = 0
                    # 只有新列表更多时才更新，或者旧列表为空/只有1张时也更新
                    if new_img_count > old_img_count or old_img_count <= 1:
                        note.image_list = json.dumps(note_data['image_list'])
                        logger.info(f"Updated image_list for {note_id}: {old_img_count} -> {new_img_count} images")
                if note_data['tags']:
                    note.tags = json.dumps(note_data['tags'])
                if note_data['ip_location']:
                    note.ip_location = note_data['ip_location']
                if cover_remote:
                    note.cover_remote = cover_remote
                if cover_local:
                    note.cover_local = cover_local
                # 【关键】保存笔记级别的xsec_token
                if note_data.get('xsec_token'):
                    note.xsec_token = note_data['xsec_token']
                    
                note.last_updated = datetime.utcnow()
            else:
                # 创建新笔记 - None值转为默认值
                note = Note(
                    note_id=note_id,
                    user_id=note_data['user_id'],
                    nickname=note_data['nickname'],
                    avatar=note_data['avatar'],
                    title=note_data['title'],
                    desc=note_data['desc'] or '',
                    type=note_data['note_type'],
                    liked_count=note_data['liked_count'] if note_data['liked_count'] is not None else 0,
                    collected_count=note_data['collected_count'] if note_data['collected_count'] is not None else 0,
                    comment_count=note_data['comment_count'] if note_data['comment_count'] is not None else 0,
                    share_count=note_data['share_count'] if note_data['share_count'] is not None else 0,
                    upload_time=note_data['upload_time'] or '',
                    video_addr=note_data['video_addr'] or '',
                    image_list=json.dumps(note_data['image_list']) if note_data['image_list'] else '[]',
                    tags=json.dumps(note_data['tags']) if note_data['tags'] else '[]',
                    ip_location=note_data['ip_location'] or '',
                    cover_remote=cover_remote or '',
                    cover_local=cover_local or '',
                    xsec_token=note_data.get('xsec_token') or '',  # 笔记级别的xsec_token
                )
                db.session.add(note)
            
            if auto_commit:
                db.session.commit()
            
            # 【性能优化】封面和媒体下载改为异步，不阻塞主流程
            queue = get_media_download_queue()
            
            # Submit cover download to async queue (with callback to update DB)
            if cover_remote:
                queue.submit_cover_download(cover_remote, note_id, callback=SyncService._update_cover_local)
            
            if download_media:
                logger.info(f"Queueing media download for note {note_id}")
                queue.submit_media_download(note_id, note_data)
                
        except Exception as e:
            # 发生异常时回滚session,避免PendingRollbackError
            db.session.rollback()
            logger.info(f"Error saving note {note_data.get('note_id')}: {e}")
            # 重新抛出异常让上层处理
            raise
    
    @staticmethod
    def _update_cover_local(note_id, local_path):
        """Callback to update cover_local in database after async download
        
        Args:
            note_id: Note ID
            local_path: Local API path for the downloaded cover
        """
        if not local_path:
            return
        try:
            # Use a new session context to avoid thread safety issues
            from flask import current_app
            # Check if we're in app context
            try:
                app = current_app._get_current_object()
            except RuntimeError:
                # Not in app context, skip update (cover will be downloaded on next sync)
                logger.debug(f"[CoverCallback] Skipping DB update for {note_id} - no app context")
                return
            
            with app.app_context():
                Note.query.filter_by(note_id=note_id).update(
                    {'cover_local': local_path},
                    synchronize_session=False
                )
                db.session.commit()
                logger.debug(f"[CoverCallback] Updated cover_local for {note_id}")
        except Exception as e:
            logger.warning(f"[CoverCallback] Failed to update cover_local for {note_id}: {e}")
            try:
                db.session.rollback()
            except:
                pass

    @staticmethod
    def _download_cover(remote_url, note_id):
        """下载封面到本地并返回可访问的API路径（使用请求池复用连接）"""
        if not remote_url:
            return None
        try:
            Config.init_paths()
            parsed = urlparse(remote_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filename = f"{note_id}_cover{ext}"
            filepath = os.path.join(Config.MEDIA_PATH, filename)
            
            # 检查文件是否存在且大小正常（>1KB）
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                return f"/api/media/{filename}"
            
            headers = get_common_headers()
            session_pool = get_request_session_pool()
            # 增加重试机制
            for attempt in range(3):
                try:
                    resp = session_pool.get(remote_url, headers=headers, stream=True, timeout=15)
                    if resp.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        logger.info(f"Successfully downloaded cover for {note_id}")
                        return f"/api/media/{filename}"
                    elif resp.status_code == 403:
                        logger.warning(f"Download cover 403 Forbidden for {note_id}, attempt {attempt+1}")
                        time.sleep(1)
                    else:
                        logger.warning(f"Download cover failed ({resp.status_code}) for {note_id}")
                except Exception as dl_err:
                    logger.warning(f"Download attempt {attempt+1} failed: {dl_err}")
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Download cover error for {note_id}: {e}")
        return None
