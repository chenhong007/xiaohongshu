"""
NoteFetcher - 笔记详情页获取器

封装笔记详情页的获取逻辑，包括：
- 统一的重试策略（使用 ApiRetryHandler）
- xsec_token 自动刷新和 fallback
- 错误分类和处理
- 与 SyncLogCollector 集成

该模块将 sync_service.py 中分散的详情页获取逻辑统一起来，
减少代码重复，提高可维护性。
"""
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from ...utils.logger import get_logger
from .retry_handler import ApiRetryHandler, ErrorType, RetryResult
from .token_manager import XsecTokenManager
from .delay_manager import get_adaptive_delay_manager
from .log_collector import SyncLogCollector

logger = get_logger('note_fetcher')


@dataclass
class FetchResult:
    """笔记获取结果"""
    success: bool
    note_data: Optional[Dict] = None
    error_type: Optional[ErrorType] = None
    error_message: str = ''
    used_fallback: bool = False  # 是否使用了 fallback token
    retry_count: int = 0
    new_xsec_token: Optional[str] = None  # 新获取的 xsec_token（用于更新数据库）
    
    @property
    def is_rate_limited(self) -> bool:
        return self.error_type == ErrorType.RATE_LIMITED
    
    @property
    def is_auth_error(self) -> bool:
        return self.error_type == ErrorType.AUTH_ERROR
    
    @property
    def is_unavailable(self) -> bool:
        return self.error_type == ErrorType.UNAVAILABLE


class NoteFetcher:
    """笔记详情页获取器
    
    统一处理笔记详情页的获取逻辑，包括：
    - 自动重试（使用 ApiRetryHandler）
    - xsec_token 自动刷新
    - 用户级 token 作为 fallback
    - 错误分类和日志记录
    
    使用示例:
        fetcher = NoteFetcher(
            data_spider=data_spider,
            token_manager=token_mgr,
            cookie_str=cookie_str,
            sync_log=sync_log  # 可选
        )
        
        result = fetcher.fetch_note_detail(
            note_id=note_id,
            note_token=note_xsec_token,
            user_id=user_id
        )
        
        if result.success:
            process_note(result.note_data)
        elif result.is_auth_error:
            handle_auth_error()
    """
    
    # 最大重试次数
    MAX_RETRIES = 3
    
    def __init__(
        self,
        data_spider,
        token_manager: XsecTokenManager,
        cookie_str: str,
        sync_log: Optional[SyncLogCollector] = None,
        on_auth_error: Optional[Callable[[str], None]] = None,
        on_rate_limit: Optional[Callable[[], None]] = None,
    ):
        """初始化笔记获取器
        
        Args:
            data_spider: Data_Spider 实例
            token_manager: XsecTokenManager 实例
            cookie_str: Cookie 字符串
            sync_log: 同步日志收集器（可选）
            on_auth_error: 认证错误回调（可选）
            on_rate_limit: 频率限制回调（可选）
        """
        self._spider = data_spider
        self._token_mgr = token_manager
        self._cookie_str = cookie_str
        self._sync_log = sync_log
        self._on_auth_error = on_auth_error
        self._on_rate_limit = on_rate_limit
        
        # 使用 ApiRetryHandler 进行错误分类
        self._retry_handler = ApiRetryHandler(
            max_retries=self.MAX_RETRIES,
            base_wait=3.0,
            max_wait=60.0,
            use_adaptive_delay=True
        )
    
    def fetch_note_detail(
        self,
        note_id: str,
        note_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> FetchResult:
        """获取笔记详情
        
        尝试顺序：
        1. 使用笔记自带的 xsec_token
        2. 使用用户级 xsec_token（缓存）
        3. 刷新用户级 xsec_token 后重试
        
        Args:
            note_id: 笔记 ID
            note_token: 笔记的 xsec_token（从列表 API 获取）
            user_id: 用户 ID（用于 token fallback）
            
        Returns:
            FetchResult: 获取结果
        """
        if not note_id:
            return FetchResult(
                success=False,
                error_message="note_id is required"
            )
        
        # 构建 URL
        primary_url = self._token_mgr.build_note_url(note_id, note_token)
        
        last_error_type = ErrorType.UNKNOWN
        last_error_msg = ''
        total_retries = 0
        rate_limited = False
        
        for retry_attempt in range(self.MAX_RETRIES):
            # 非首次重试需要等待
            if retry_attempt > 0:
                wait_time = self._get_wait_time(retry_attempt - 1, last_error_type)
                logger.debug(f"Note {note_id}: retry {retry_attempt}/{self.MAX_RETRIES}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            
            total_retries = retry_attempt
            
            # 尝试获取详情
            try:
                success, msg, note_info = self._spider.spider_note(primary_url, self._cookie_str)
            except Exception as e:
                success, msg, note_info = False, str(e), None
            
            last_error_msg = msg
            
            # 成功获取
            if success and note_info:
                return FetchResult(
                    success=True,
                    note_data=note_info,
                    retry_count=total_retries
                )
            
            # 分类错误
            error_type = ApiRetryHandler.classify_error(msg)
            last_error_type = error_type
            
            logger.debug(f"Note {note_id}: fetch failed - {msg} (type={error_type.value})")
            
            # 处理不同类型的错误
            
            # 1. 认证错误 - 立即返回，不重试
            if error_type == ErrorType.AUTH_ERROR:
                self._log_issue(SyncLogCollector.TYPE_AUTH_ERROR, note_id, msg)
                if self._on_auth_error:
                    self._on_auth_error(msg)
                return FetchResult(
                    success=False,
                    error_type=error_type,
                    error_message=msg,
                    retry_count=total_retries
                )
            
            # 2. 频率限制 - 记录并等待后重试
            if error_type == ErrorType.RATE_LIMITED:
                rate_limited = True
                self._log_issue(
                    SyncLogCollector.TYPE_RATE_LIMITED, 
                    note_id, 
                    msg,
                    extra={'retry': retry_attempt + 1}
                )
                if self._on_rate_limit:
                    self._on_rate_limit()
                get_adaptive_delay_manager().record_rate_limit()
                
                # 频率限制需要更长的等待时间
                wait_time = get_adaptive_delay_manager().get_rate_limit_wait()
                time.sleep(wait_time)
                continue
            
            # 3. 资源不可用 - 立即返回，不重试
            if error_type == ErrorType.UNAVAILABLE:
                logger.warning(f"Note {note_id} unavailable: {msg}")
                self._log_issue(SyncLogCollector.TYPE_UNAVAILABLE, note_id, msg)
                return FetchResult(
                    success=False,
                    error_type=error_type,
                    error_message=msg,
                    retry_count=total_retries
                )
            
            # 4. Token 错误 - 尝试 fallback
            if error_type == ErrorType.TOKEN_ERROR or '暂时无法浏览' in str(msg):
                fallback_result = self._try_token_fallback(note_id, user_id, retry_attempt)
                if fallback_result.success:
                    return fallback_result
                
                # Fallback 失败，记录并继续重试
                if not fallback_result.error_message:
                    self._log_issue(
                        SyncLogCollector.TYPE_TOKEN_REFRESH,
                        note_id,
                        f"xsec_token invalid: {msg}"
                    )
                continue
            
            # 5. Items 缺失 - xsec_token 无效，直接从用户笔记列表获取新 token
            if error_type == ErrorType.ITEMS_MISSING:
                logger.warning(f"Note {note_id} API响应缺少items字段（xsec_token无效）: {msg}")
                
                # 直接从用户笔记列表获取新的笔记级 token
                if user_id:
                    fallback_result = self._try_token_fallback(note_id, user_id, retry_attempt)
                    if fallback_result.success:
                        return fallback_result
                    # Fallback 失败，不再重试（token 问题无法通过简单重试解决）
                    logger.warning(f"Note {note_id} 无法获取有效的 xsec_token")
                    return FetchResult(
                        success=False,
                        error_type=error_type,
                        error_message="xsec_token 无效且无法刷新",
                        retry_count=total_retries
                    )
                else:
                    logger.warning(f"Note {note_id} 缺少 user_id，无法刷新 token")
                continue
            
            # 6. 其他错误 - 记录并继续重试
            logger.warning(f"Failed to get note detail for {note_id}: {msg}")
            self._log_issue(SyncLogCollector.TYPE_FETCH_FAILED, note_id, msg)
        
        # 所有重试都失败
        # 如果是频率限制，额外等待
        if rate_limited:
            total_wait = get_adaptive_delay_manager().get_rate_limit_wait() * 1.5
            time.sleep(total_wait)
        
        return FetchResult(
            success=False,
            error_type=last_error_type,
            error_message=last_error_msg,
            retry_count=total_retries
        )
    
    def _try_token_fallback(
        self,
        note_id: str,
        user_id: Optional[str],
        retry_attempt: int,
        force_refresh: bool = False
    ) -> FetchResult:
        """尝试从用户笔记列表获取笔记级 token 并重试
        
        注意：用户级 token 不能用于获取笔记详情，必须使用笔记级 token。
        因此直接从用户笔记列表 API 获取该笔记的 xsec_token。
        
        Args:
            note_id: 笔记 ID
            user_id: 用户 ID
            retry_attempt: 当前重试次数
            force_refresh: 未使用，保留参数兼容性
            
        Returns:
            FetchResult: 获取结果（success=False 表示 fallback 失败）
        """
        if not user_id:
            return FetchResult(success=False, error_message="No user_id for fallback")
        
        # 直接从用户笔记列表获取笔记级 token（用户级 token 不能获取笔记详情）
        logger.info(f"Note {note_id} xsec_token 失效，从用户笔记列表获取新 token...")
        note_token = self._token_mgr.refresh_note_token(note_id, user_id)
        
        if note_token:
            note_url = self._token_mgr.build_note_url(note_id, note_token)
            try:
                success, msg, note_info = self._spider.spider_note(note_url, self._cookie_str)
                if success and note_info:
                    logger.info(f"Note {note_id} 使用新 token 获取成功")
                    return FetchResult(
                        success=True,
                        note_data=note_info,
                        used_fallback=True,
                        new_xsec_token=note_token  # 返回新 token 用于更新数据库
                    )
                else:
                    self._log_issue(
                        SyncLogCollector.TYPE_TOKEN_REFRESH,
                        note_id,
                        f"新 token 仍然失败: {msg}"
                    )
            except Exception as e:
                self._log_issue(
                    SyncLogCollector.TYPE_TOKEN_REFRESH,
                    note_id,
                    f"使用新 token 时发生异常: {e}"
                )
        else:
            self._log_issue(
                SyncLogCollector.TYPE_TOKEN_REFRESH,
                note_id,
                "无法从用户笔记列表获取新 token"
            )
        
        return FetchResult(success=False, error_message="Failed to refresh note token")
    
    def _get_wait_time(self, retry_attempt: int, error_type: ErrorType) -> float:
        """计算等待时间
        
        Args:
            retry_attempt: 当前重试次数 (0-based)
            error_type: 错误类型
            
        Returns:
            等待时间（秒）
        """
        if error_type == ErrorType.RATE_LIMITED:
            return get_adaptive_delay_manager().get_rate_limit_wait()
        
        # 指数退避 + 随机抖动
        base = 3.0 * (2 ** retry_attempt)
        jitter = random.uniform(0.8, 1.2)
        return min(base * jitter, 60.0)
    
    def _log_issue(
        self,
        issue_type: str,
        note_id: str,
        message: str,
        extra: Optional[Dict] = None
    ) -> None:
        """记录问题到同步日志
        
        Args:
            issue_type: 问题类型
            note_id: 笔记 ID
            message: 错误消息
            extra: 额外信息
        """
        if self._sync_log:
            self._sync_log.add_issue(
                issue_type,
                note_id=note_id,
                message=message,
                extra=extra
            )


class BatchNoteFetcher:
    """批量笔记获取器
    
    用于批量获取多个笔记的详情，支持：
    - 自适应延迟（避免触发频率限制）
    - 进度回调
    - 统一的错误处理
    
    使用示例:
        batch_fetcher = BatchNoteFetcher(
            data_spider=data_spider,
            token_manager=token_mgr,
            cookie_str=cookie_str
        )
        
        results = batch_fetcher.fetch_notes(
            notes=[{'note_id': '...', 'xsec_token': '...'}],
            user_id=user_id,
            on_progress=lambda idx, total: print(f"{idx}/{total}")
        )
    """
    
    def __init__(
        self,
        data_spider,
        token_manager: XsecTokenManager,
        cookie_str: str,
        sync_log: Optional[SyncLogCollector] = None,
        on_auth_error: Optional[Callable[[str], None]] = None,
        on_rate_limit: Optional[Callable[[], None]] = None,
    ):
        """初始化批量获取器"""
        self._fetcher = NoteFetcher(
            data_spider=data_spider,
            token_manager=token_manager,
            cookie_str=cookie_str,
            sync_log=sync_log,
            on_auth_error=on_auth_error,
            on_rate_limit=on_rate_limit
        )
        self._delay_manager = get_adaptive_delay_manager()
    
    def fetch_notes(
        self,
        notes: list,
        user_id: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, FetchResult]:
        """批量获取笔记详情
        
        Args:
            notes: 笔记列表，每个元素包含 note_id 和 xsec_token
            user_id: 用户 ID
            on_progress: 进度回调 (current_index, total)
            stop_check: 停止检查回调，返回 True 时停止
            
        Returns:
            Dict[note_id, FetchResult]: 获取结果字典
        """
        results = {}
        total = len(notes)
        
        for idx, note in enumerate(notes):
            # 检查是否需要停止
            if stop_check and stop_check():
                logger.info("Batch fetch stopped by user")
                break
            
            note_id = note.get('note_id') or note.get('id')
            note_token = note.get('xsec_token', '')
            
            if not note_id:
                continue
            
            # 获取详情
            result = self._fetcher.fetch_note_detail(
                note_id=note_id,
                note_token=note_token,
                user_id=user_id
            )
            
            results[note_id] = result
            
            # 认证错误时立即停止
            if result.is_auth_error:
                logger.warning("Auth error detected, stopping batch fetch")
                break
            
            # 进度回调
            if on_progress:
                on_progress(idx + 1, total)
            
            # 自适应延迟
            if idx < total - 1:  # 最后一个不需要延迟
                self._sleep_with_jitter()
        
        return results
    
    def _sleep_with_jitter(self) -> None:
        """带抖动的延迟"""
        delay = self._delay_manager.get_delay()
        
        # 15% 概率额外延迟
        if random.random() < 0.15:
            delay += random.uniform(5.0, 20.0)
        
        logger.debug(f"[BatchFetcher] Sleeping for {delay:.1f}s")
        time.sleep(delay)

