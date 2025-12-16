"""
Sync State Manager - 同步状态统一管理

此模块提供同步状态的统一管理，包括：
- 账户状态更新（processing, completed, failed, cancelled）
- 心跳更新（防止任务被误判为僵死）
- 进度广播（实时推送同步进度到前端）

设计目标：
- 消除 sync_service.py 中的重复状态管理代码
- 提供清晰的状态转换接口
- 自动处理心跳和进度广播
"""
import threading
from datetime import datetime
from typing import Dict, Optional, Any

from ...extensions import db
from ...models import Account
from ...utils.logger import get_logger
from ..sync_log_broadcaster import sync_log_broadcaster

logger = get_logger('state_manager')


class SyncStateManager:
    """同步状态统一管理器
    
    管理单个账户的同步状态，包括：
    - 状态转换（start -> processing -> completed/failed/cancelled）
    - 心跳更新（每次进度更新时自动更新）
    - 进度广播（通过 WebSocket 实时推送）
    
    使用示例:
        >>> state = SyncStateManager(account_id=1, sync_mode='deep')
        >>> state.start()
        >>> for i in range(total):
        ...     # 处理笔记...
        ...     state.update_progress(i + 1, total)
        >>> state.complete(summary={'success': 100})
    
    线程安全：
        所有状态更新操作都是线程安全的
    """
    
    # 同步状态常量
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    
    # 进度广播间隔（每处理多少条笔记广播一次）
    BROADCAST_INTERVAL = 5
    
    # 心跳更新间隔（与广播间隔保持一致）
    HEARTBEAT_INTERVAL = 5
    
    def __init__(
        self,
        account_id: int,
        sync_mode: str,
        account_name: Optional[str] = None
    ):
        """初始化状态管理器
        
        Args:
            account_id: 账户 ID
            sync_mode: 同步模式 ('fast' 或 'deep')
            account_name: 账户名称（用于日志显示，可选）
        """
        self.account_id = account_id
        self.sync_mode = sync_mode
        self.account_name = account_name
        
        # 状态追踪
        self._status = self.STATUS_PENDING
        self._progress = 0
        self._loaded = 0
        self._total = 0
        self._new_notes = 0
        self._error_message: Optional[str] = None
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        
        # 线程安全锁
        self._lock = threading.Lock()
        
        # 上次广播的进度（用于避免重复广播）
        self._last_broadcast_loaded = -1
    
    @property
    def status(self) -> str:
        """获取当前状态"""
        with self._lock:
            return self._status
    
    @property
    def progress(self) -> int:
        """获取当前进度百分比"""
        with self._lock:
            return self._progress
    
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        with self._lock:
            return self._status == self.STATUS_PROCESSING
    
    @property
    def is_finished(self) -> bool:
        """检查是否已完成（包括成功、失败、取消）"""
        with self._lock:
            return self._status in (
                self.STATUS_COMPLETED,
                self.STATUS_FAILED,
                self.STATUS_CANCELLED
            )
    
    def start(self, total: int = 0) -> bool:
        """开始同步，初始化状态
        
        Args:
            total: 预计处理的笔记总数
            
        Returns:
            True 如果成功开始，False 如果账户不存在
        """
        with self._lock:
            self._status = self.STATUS_PROCESSING
            self._progress = 0
            self._loaded = 0
            self._total = total
            self._new_notes = 0
            self._error_message = None
            self._start_time = datetime.utcnow()
            self._end_time = None
            self._last_broadcast_loaded = -1
        
        # 更新数据库
        try:
            account = Account.query.get(self.account_id)
            if not account:
                logger.warning(f"Account {self.account_id} not found")
                return False
            
            # 缓存账户名称
            if not self.account_name:
                self.account_name = account.name or account.user_id
            
            account.status = self.STATUS_PROCESSING
            account.progress = 0
            account.loaded_msgs = 0
            account.total_msgs = total
            account.error_message = None
            account.sync_heartbeat = datetime.utcnow()
            
            # 深度同步时清空旧日志
            if self.sync_mode == 'deep':
                account.sync_logs = None
            
            db.session.commit()
            
            # 广播开始同步
            sync_log_broadcaster.info(
                f"开始同步: {self.account_name}",
                account_id=self.account_id,
                account_name=self.account_name
            )
            
            logger.info(f"[StateManager] Account {self.account_id} sync started, mode={self.sync_mode}")
            return True
            
        except Exception as e:
            logger.error(f"[StateManager] Failed to start sync for account {self.account_id}: {e}")
            db.session.rollback()
            return False
    
    def set_total(self, total: int) -> None:
        """设置笔记总数（可在 start 后调用）
        
        Args:
            total: 笔记总数
        """
        with self._lock:
            self._total = total
        
        try:
            Account.query.filter_by(id=self.account_id).update(
                {'total_msgs': total},
                synchronize_session=False
            )
            db.session.commit()
            
            sync_log_broadcaster.info(
                f"获取到 {total} 条笔记",
                account_id=self.account_id,
                account_name=self.account_name,
                extra={'total': total}
            )
        except Exception as e:
            logger.warning(f"[StateManager] Failed to set total for account {self.account_id}: {e}")
            db.session.rollback()
    
    def update_progress(
        self,
        loaded: int,
        total: Optional[int] = None,
        new_notes: Optional[int] = None,
        force_broadcast: bool = False
    ) -> None:
        """更新进度（包含心跳和广播）
        
        此方法会自动：
        1. 更新心跳时间戳
        2. 根据间隔决定是否广播进度
        
        Args:
            loaded: 已处理的笔记数
            total: 笔记总数（可选，不传则使用之前设置的值）
            new_notes: 新增笔记数（可选）
            force_broadcast: 强制广播（用于最后一条）
        """
        with self._lock:
            self._loaded = loaded
            if total is not None:
                self._total = total
            if new_notes is not None:
                self._new_notes = new_notes
            
            # 计算进度百分比
            if self._total > 0:
                self._progress = int((loaded / self._total) * 100)
            else:
                self._progress = 100 if loaded > 0 else 0
            
            # 检查是否需要广播
            should_broadcast = (
                force_broadcast or
                loaded == self._total or  # 最后一条
                (loaded - self._last_broadcast_loaded) >= self.BROADCAST_INTERVAL
            )
            
            if should_broadcast:
                self._last_broadcast_loaded = loaded
                progress = self._progress
                total_val = self._total
                new_notes_val = self._new_notes
            else:
                should_broadcast = False
        
        # 更新数据库（批量提交，减少 IO）
        if should_broadcast:
            try:
                Account.query.filter_by(id=self.account_id).update(
                    {
                        'loaded_msgs': loaded,
                        'progress': progress,
                        'sync_heartbeat': datetime.utcnow()
                    },
                    synchronize_session=False
                )
                db.session.commit()
                
                # 广播进度
                sync_log_broadcaster.broadcast_progress(
                    account_id=self.account_id,
                    status=self.STATUS_PROCESSING,
                    progress=progress,
                    loaded_msgs=loaded,
                    total_msgs=total_val,
                    new_notes=new_notes_val
                )
            except Exception as e:
                logger.warning(f"[StateManager] Failed to update progress: {e}")
                db.session.rollback()
    
    def update_heartbeat(self) -> None:
        """单独更新心跳（不更新进度）
        
        用于长时间处理单个笔记时保持心跳
        """
        try:
            Account.query.filter_by(id=self.account_id).update(
                {'sync_heartbeat': datetime.utcnow()},
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"[StateManager] Failed to update heartbeat: {e}")
            db.session.rollback()
    
    def complete(
        self,
        summary: Optional[Dict[str, Any]] = None,
        sync_logs: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """完成同步
        
        Args:
            summary: 同步摘要（用于广播）
            sync_logs: 同步日志 JSON 字符串（存储到数据库）
            error_message: 警告信息（同步完成但有问题）
        """
        with self._lock:
            self._status = self.STATUS_COMPLETED
            self._progress = 100
            self._end_time = datetime.utcnow()
            if error_message:
                self._error_message = error_message
        
        try:
            update_data = {
                'status': self.STATUS_COMPLETED,
                'progress': 100,
                'loaded_msgs': self._total,
                'last_sync': datetime.utcnow(),
                'sync_heartbeat': None  # 清除心跳
            }
            
            if sync_logs:
                update_data['sync_logs'] = sync_logs
            if error_message:
                update_data['error_message'] = error_message
            
            Account.query.filter_by(id=self.account_id).update(
                update_data,
                synchronize_session=False
            )
            db.session.commit()
            
            # 广播完成
            sync_log_broadcaster.broadcast_completed(
                self.account_id,
                self.STATUS_COMPLETED,
                summary
            )
            
            logger.info(
                f"[StateManager] Account {self.account_id} sync completed, "
                f"total={self._total}, new_notes={self._new_notes}"
            )
            
        except Exception as e:
            logger.error(f"[StateManager] Failed to mark complete: {e}")
            db.session.rollback()
    
    def fail(self, error_msg: str, sync_logs: Optional[str] = None) -> None:
        """标记失败
        
        Args:
            error_msg: 错误信息
            sync_logs: 同步日志 JSON 字符串（可选）
        """
        with self._lock:
            self._status = self.STATUS_FAILED
            self._error_message = error_msg
            self._end_time = datetime.utcnow()
        
        try:
            update_data = {
                'status': self.STATUS_FAILED,
                'error_message': error_msg[:500] if error_msg else 'Unknown error',
                'sync_heartbeat': None
            }
            
            if sync_logs:
                update_data['sync_logs'] = sync_logs
            
            Account.query.filter_by(id=self.account_id).update(
                update_data,
                synchronize_session=False
            )
            db.session.commit()
            
            # 广播失败
            sync_log_broadcaster.error(
                f"同步失败: {error_msg}",
                account_id=self.account_id,
                account_name=self.account_name
            )
            sync_log_broadcaster.broadcast_completed(
                self.account_id,
                self.STATUS_FAILED,
                {'error': error_msg}
            )
            
            logger.warning(f"[StateManager] Account {self.account_id} sync failed: {error_msg}")
            
        except Exception as e:
            logger.error(f"[StateManager] Failed to mark failure: {e}")
            db.session.rollback()
    
    def cancel(self, reason: Optional[str] = None) -> None:
        """取消同步
        
        Args:
            reason: 取消原因（可选）
        """
        mode_name = '深度同步' if self.sync_mode == 'deep' else '急速同步'
        cancel_msg = reason or f"用户取消{mode_name}"
        
        with self._lock:
            self._status = self.STATUS_CANCELLED
            self._error_message = cancel_msg
            self._end_time = datetime.utcnow()
        
        try:
            Account.query.filter_by(id=self.account_id).update(
                {
                    'status': self.STATUS_FAILED,  # 前端显示为失败
                    'error_message': cancel_msg,
                    'sync_heartbeat': None
                },
                synchronize_session=False
            )
            db.session.commit()
            
            # 广播取消
            sync_log_broadcaster.broadcast_completed(
                self.account_id,
                'cancelled'
            )
            
            logger.info(f"[StateManager] Account {self.account_id} sync cancelled: {cancel_msg}")
            
        except Exception as e:
            logger.error(f"[StateManager] Failed to mark cancelled: {e}")
            db.session.rollback()
    
    def increment_new_notes(self, count: int = 1) -> None:
        """增加新增笔记计数
        
        Args:
            count: 增加的数量
        """
        with self._lock:
            self._new_notes += count
    
    def get_new_notes_count(self) -> int:
        """获取当前新增笔记数"""
        with self._lock:
            return self._new_notes
    
    def get_stats(self) -> Dict[str, Any]:
        """获取当前统计信息
        
        Returns:
            包含状态、进度、计数等信息的字典
        """
        with self._lock:
            return {
                'account_id': self.account_id,
                'sync_mode': self.sync_mode,
                'status': self._status,
                'progress': self._progress,
                'loaded': self._loaded,
                'total': self._total,
                'new_notes': self._new_notes,
                'error_message': self._error_message,
                'start_time': self._start_time.isoformat() if self._start_time else None,
                'end_time': self._end_time.isoformat() if self._end_time else None,
            }


def batch_mark_failed(account_ids: set, error_message: str) -> int:
    """批量标记账户为失败状态
    
    用于在致命错误（如 Cookie 失效）时快速标记所有待处理账户
    
    Args:
        account_ids: 账户 ID 集合
        error_message: 错误信息
        
    Returns:
        成功标记的账户数量
    """
    if not account_ids:
        return 0
    
    try:
        affected = Account.query.filter(Account.id.in_(list(account_ids))).update(
            {
                'status': SyncStateManager.STATUS_FAILED,
                'error_message': error_message[:500] if error_message else 'Unknown error',
                'progress': 0,
                'sync_heartbeat': None
            },
            synchronize_session=False
        )
        db.session.commit()
        
        logger.info(f"[StateManager] Batch marked {affected} accounts as failed")
        return affected
        
    except Exception as e:
        logger.error(f"[StateManager] Failed to batch mark accounts as failed: {e}")
        db.session.rollback()
        return 0

