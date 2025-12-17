"""
Account Health Tracker - 账号健康状态追踪器

用于追踪和更新账号的健康状态，包括：
- Cookie 过期/失效
- 限流状态
- xsec_token 无效
- 风控限制
- 其他错误

健康状态会实时反馈到前端，在左下角账号位置显示警告提示。
"""
from datetime import datetime
from typing import Optional

from ...extensions import db
from ...models import Account
from ...utils.logger import get_logger
from ..sync_log_broadcaster import sync_log_broadcaster

logger = get_logger('health_tracker')


class HealthStatus:
    """账号健康状态常量"""
    HEALTHY = 'healthy'                 # 正常
    COOKIE_EXPIRED = 'cookie_expired'   # Cookie 过期/失效
    RATE_LIMITED = 'rate_limited'       # 被限流
    TOKEN_INVALID = 'token_invalid'     # xsec_token 无效
    RISK_CONTROL = 'risk_control'       # 风控限制
    UNKNOWN_ERROR = 'unknown_error'     # 未知错误


class AccountHealthTracker:
    """账号健康状态追踪器
    
    用于在同步过程中追踪和更新账号的健康状态。
    健康状态会通过 WebSocket 实时推送到前端。
    
    使用示例:
        tracker = AccountHealthTracker(account_id=26, account_name='AI搭子小卖部')
        
        # 检测到 Cookie 过期
        tracker.set_cookie_expired('Cookie 已失效，请重新登录')
        
        # 检测到限流
        tracker.set_rate_limited('访问频次异常，已触发限流保护')
        
        # 恢复正常
        tracker.set_healthy()
    """
    
    def __init__(self, account_id: int, account_name: Optional[str] = None):
        """初始化健康追踪器
        
        Args:
            account_id: 账号 ID
            account_name: 账号名称（用于日志和前端显示）
        """
        self.account_id = account_id
        self.account_name = account_name or f'Account {account_id}'
        self._current_status = HealthStatus.HEALTHY
        self._rate_limit_count = 0  # 连续限流次数
    
    def _update_health_status(
        self, 
        status: str, 
        message: Optional[str] = None,
        broadcast: bool = True
    ) -> None:
        """更新账号健康状态
        
        Args:
            status: 健康状态
            message: 状态详细信息
            broadcast: 是否广播到前端
        """
        try:
            account = Account.query.get(self.account_id)
            if not account:
                logger.warning(f"[HealthTracker] Account {self.account_id} not found")
                return
            
            # 更新数据库
            account.health_status = status
            account.health_message = message
            account.health_updated_at = datetime.utcnow()
            db.session.commit()
            
            self._current_status = status
            
            logger.info(
                f"[HealthTracker] Account {self.account_name} (id={self.account_id}) "
                f"health status: {status}, message: {message}"
            )
            
            # 广播到前端
            if broadcast:
                self._broadcast_health_status(status, message)
                
        except Exception as e:
            logger.error(f"[HealthTracker] Failed to update health status: {e}")
            db.session.rollback()
    
    def _broadcast_health_status(self, status: str, message: Optional[str] = None) -> None:
        """广播健康状态到前端
        
        Args:
            status: 健康状态
            message: 状态详细信息
        """
        # 构建状态消息
        status_messages = {
            HealthStatus.COOKIE_EXPIRED: 'Cookie 已失效',
            HealthStatus.RATE_LIMITED: '访问被限流',
            HealthStatus.TOKEN_INVALID: 'Token 无效',
            HealthStatus.RISK_CONTROL: '账号被风控',
            HealthStatus.UNKNOWN_ERROR: '同步异常',
            HealthStatus.HEALTHY: '状态正常',
        }
        
        display_message = message or status_messages.get(status, '未知状态')
        
        # 使用 sync_log_broadcaster 广播账号健康状态
        sync_log_broadcaster.broadcast(
            level='error' if status != HealthStatus.HEALTHY else 'info',
            message=display_message,
            account_id=self.account_id,
            account_name=self.account_name,
            extra={
                'type': 'account_health',
                'health_status': status,
                'health_message': message,
            }
        )
    
    def set_healthy(self) -> None:
        """设置账号状态为正常"""
        self._rate_limit_count = 0
        if self._current_status != HealthStatus.HEALTHY:
            self._update_health_status(HealthStatus.HEALTHY, '账号状态正常')
    
    def set_cookie_expired(self, message: Optional[str] = None) -> None:
        """设置账号状态为 Cookie 过期
        
        Args:
            message: 错误详细信息
        """
        self._update_health_status(
            HealthStatus.COOKIE_EXPIRED,
            message or 'Cookie 已失效，请重新登录'
        )
    
    def set_rate_limited(self, message: Optional[str] = None, count: int = 0) -> None:
        """设置账号状态为被限流
        
        Args:
            message: 错误详细信息
            count: 限流次数
        """
        self._rate_limit_count = count if count > 0 else self._rate_limit_count + 1
        msg = message or f'访问频次异常，已触发限流保护 (累计 {self._rate_limit_count} 次)'
        self._update_health_status(HealthStatus.RATE_LIMITED, msg)
    
    def set_token_invalid(self, message: Optional[str] = None) -> None:
        """设置账号状态为 Token 无效
        
        Args:
            message: 错误详细信息
        """
        self._update_health_status(
            HealthStatus.TOKEN_INVALID,
            message or 'xsec_token 无效，无法获取笔记详情'
        )
    
    def set_risk_control(self, message: Optional[str] = None) -> None:
        """设置账号状态为风控限制
        
        Args:
            message: 错误详细信息
        """
        self._update_health_status(
            HealthStatus.RISK_CONTROL,
            message or '账号可能被风控，请检查小红书账号状态'
        )
    
    def set_unknown_error(self, message: Optional[str] = None) -> None:
        """设置账号状态为未知错误
        
        Args:
            message: 错误详细信息
        """
        self._update_health_status(
            HealthStatus.UNKNOWN_ERROR,
            message or '同步过程中发生未知错误'
        )
    
    def record_rate_limit(self) -> int:
        """记录一次限流事件
        
        Returns:
            当前连续限流次数
        """
        self._rate_limit_count += 1
        return self._rate_limit_count
    
    def reset_rate_limit_count(self) -> None:
        """重置限流计数"""
        self._rate_limit_count = 0
    
    @property
    def current_status(self) -> str:
        """获取当前健康状态"""
        return self._current_status
    
    @property
    def rate_limit_count(self) -> int:
        """获取当前限流次数"""
        return self._rate_limit_count


def update_account_health(
    account_id: int,
    status: str,
    message: Optional[str] = None,
    account_name: Optional[str] = None
) -> None:
    """便捷函数：更新账号健康状态
    
    Args:
        account_id: 账号 ID
        status: 健康状态 (使用 HealthStatus 常量)
        message: 状态详细信息
        account_name: 账号名称
    """
    tracker = AccountHealthTracker(account_id, account_name)
    tracker._update_health_status(status, message)


def mark_account_cookie_expired(account_id: int, message: Optional[str] = None) -> None:
    """便捷函数：标记账号 Cookie 过期"""
    tracker = AccountHealthTracker(account_id)
    tracker.set_cookie_expired(message)


def mark_account_rate_limited(account_id: int, message: Optional[str] = None, count: int = 0) -> None:
    """便捷函数：标记账号被限流"""
    tracker = AccountHealthTracker(account_id)
    tracker.set_rate_limited(message, count)


def mark_account_healthy(account_id: int) -> None:
    """便捷函数：标记账号状态正常"""
    tracker = AccountHealthTracker(account_id)
    tracker.set_healthy()

