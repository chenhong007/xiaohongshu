"""
API Retry Handler - 统一的API请求重试和错误处理

该模块提供:
- 错误类型分类 (rate_limited, auth_error, token_error等)
- 带重试的API调用执行器
- 统一的fallback处理逻辑
- 与AdaptiveDelayManager集成的等待策略
"""
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from ...utils.logger import get_logger
from .delay_manager import get_adaptive_delay_manager

logger = get_logger('retry_handler')

T = TypeVar('T')


class ErrorType(str, Enum):
    """API错误类型枚举"""
    RATE_LIMITED = 'rate_limited'      # 频率限制
    AUTH_ERROR = 'auth_error'          # 认证错误 (Cookie失效)
    TOKEN_ERROR = 'token_error'        # xsec_token错误
    UNAVAILABLE = 'unavailable'        # 资源不可用 (笔记不存在等)
    ITEMS_MISSING = 'items_missing'    # API响应缺少items字段
    NETWORK_ERROR = 'network_error'    # 网络错误
    UNKNOWN = 'unknown'                # 未知错误


@dataclass
class RetryResult:
    """重试执行结果"""
    success: bool
    error_type: Optional[ErrorType]
    message: str
    data: Any = None
    retry_count: int = 0
    
    @property
    def is_rate_limited(self) -> bool:
        return self.error_type == ErrorType.RATE_LIMITED
    
    @property
    def is_auth_error(self) -> bool:
        return self.error_type == ErrorType.AUTH_ERROR
    
    @property
    def is_token_error(self) -> bool:
        return self.error_type == ErrorType.TOKEN_ERROR
    
    @property
    def is_recoverable(self) -> bool:
        """是否可恢复的错误 (可以通过重试解决)"""
        return self.error_type in (
            ErrorType.RATE_LIMITED,
            ErrorType.ITEMS_MISSING,
            ErrorType.NETWORK_ERROR,
        )


class ApiRetryHandler:
    """API请求重试和错误处理器
    
    统一处理各种API调用的重试逻辑，包括:
    - 错误类型自动分类
    - 智能重试策略
    - 与自适应延迟管理器集成
    - 可配置的回调处理
    
    Example:
        >>> handler = ApiRetryHandler(max_retries=3)
        >>> result = handler.execute(
        ...     func=lambda: api.get_note(note_id, cookie),
        ...     on_rate_limit=lambda: delay_manager.record_rate_limit()
        ... )
        >>> if result.success:
        ...     process_data(result.data)
        >>> elif result.is_auth_error:
        ...     invalidate_cookie()
    """
    
    # 错误关键词映射
    _RATE_LIMIT_KEYWORDS = ['频次异常', '频繁操作', '请求过于频繁', '频次', 'rate limit']
    _AUTH_ERROR_KEYWORDS = ['未登录', '登录已过期', '需要登录', '401', '403', 
                           'Unauthorized', '凭据不合法', '凭据无效', '10062']
    _TOKEN_ERROR_KEYWORDS = ['xsec', '签名', 'token', '参数错误', 'invalid signature']
    _UNAVAILABLE_KEYWORDS = ['暂时无法浏览', '笔记不存在', '已删除', '不存在', '404']
    _ITEMS_MISSING_KEYWORDS = ["'items'", 'items', "缺少'items'", 'missing items']
    _NETWORK_ERROR_KEYWORDS = ['timeout', 'connection', 'network', '连接', '超时']
    
    def __init__(
        self,
        max_retries: int = 3,
        base_wait: float = 3.0,
        max_wait: float = 60.0,
        use_adaptive_delay: bool = True,
    ):
        """初始化重试处理器
        
        Args:
            max_retries: 最大重试次数
            base_wait: 基础等待时间 (秒)
            max_wait: 最大等待时间 (秒)
            use_adaptive_delay: 是否使用自适应延迟管理器
        """
        self.max_retries = max_retries
        self.base_wait = base_wait
        self.max_wait = max_wait
        self.use_adaptive_delay = use_adaptive_delay
    
    @staticmethod
    def classify_error(msg: str) -> ErrorType:
        """分类错误类型
        
        Args:
            msg: 错误消息字符串
            
        Returns:
            ErrorType: 错误类型枚举值
        """
        if not msg:
            return ErrorType.UNKNOWN
        
        msg_lower = str(msg).lower()
        msg_str = str(msg)
        
        # 按优先级检查错误类型
        # 1. 认证错误 (最高优先级，需要立即处理)
        if any(kw in msg_str for kw in ApiRetryHandler._AUTH_ERROR_KEYWORDS):
            return ErrorType.AUTH_ERROR
        
        # 2. 频率限制
        if any(kw in msg_str for kw in ApiRetryHandler._RATE_LIMIT_KEYWORDS):
            return ErrorType.RATE_LIMITED
        
        # 3. Token错误
        if any(kw.lower() in msg_lower for kw in ApiRetryHandler._TOKEN_ERROR_KEYWORDS):
            return ErrorType.TOKEN_ERROR
        
        # 4. 资源不可用
        if any(kw in msg_str for kw in ApiRetryHandler._UNAVAILABLE_KEYWORDS):
            return ErrorType.UNAVAILABLE
        
        # 5. Items字段缺失
        if any(kw.lower() in msg_lower for kw in ApiRetryHandler._ITEMS_MISSING_KEYWORDS):
            return ErrorType.ITEMS_MISSING
        
        # 6. 网络错误
        if any(kw.lower() in msg_lower for kw in ApiRetryHandler._NETWORK_ERROR_KEYWORDS):
            return ErrorType.NETWORK_ERROR
        
        return ErrorType.UNKNOWN
    
    @staticmethod
    def is_rate_limited(msg: str) -> bool:
        """检查是否是频率限制错误"""
        return ApiRetryHandler.classify_error(msg) == ErrorType.RATE_LIMITED
    
    @staticmethod
    def is_auth_error(msg: str) -> bool:
        """检查是否是认证错误"""
        return ApiRetryHandler.classify_error(msg) == ErrorType.AUTH_ERROR
    
    @staticmethod
    def is_token_error(msg: str) -> bool:
        """检查是否是Token错误"""
        return ApiRetryHandler.classify_error(msg) == ErrorType.TOKEN_ERROR
    
    @staticmethod
    def is_unavailable(msg: str) -> bool:
        """检查是否是资源不可用错误"""
        return ApiRetryHandler.classify_error(msg) == ErrorType.UNAVAILABLE
    
    @staticmethod
    def is_items_missing(msg: str) -> bool:
        """检查是否是items字段缺失错误"""
        return ApiRetryHandler.classify_error(msg) == ErrorType.ITEMS_MISSING
    
    def _get_wait_time(self, retry_attempt: int, error_type: ErrorType) -> float:
        """计算等待时间
        
        Args:
            retry_attempt: 当前重试次数 (0-based)
            error_type: 错误类型
            
        Returns:
            等待时间 (秒)
        """
        if error_type == ErrorType.RATE_LIMITED and self.use_adaptive_delay:
            # 频率限制使用自适应延迟管理器
            return get_adaptive_delay_manager().get_rate_limit_wait()
        
        # 指数退避 + 随机抖动
        base = self.base_wait * (2 ** retry_attempt)
        jitter = random.uniform(0.8, 1.2)
        wait = min(base * jitter, self.max_wait)
        
        # items缺失错误需要更长等待时间
        if error_type == ErrorType.ITEMS_MISSING:
            wait = random.uniform(5, 10) * (retry_attempt + 1)
        
        return wait
    
    def _should_retry(self, error_type: ErrorType, retry_attempt: int) -> bool:
        """判断是否应该重试
        
        Args:
            error_type: 错误类型
            retry_attempt: 当前重试次数 (0-based)
            
        Returns:
            是否应该重试
        """
        if retry_attempt >= self.max_retries - 1:
            return False
        
        # 认证错误不重试
        if error_type == ErrorType.AUTH_ERROR:
            return False
        
        # 资源不可用不重试
        if error_type == ErrorType.UNAVAILABLE:
            return False
        
        # 其他错误可以重试
        return True
    
    def execute(
        self,
        func: Callable[[], Tuple[bool, str, T]],
        on_rate_limit: Optional[Callable[[], None]] = None,
        on_token_error: Optional[Callable[[], Optional[Tuple[bool, str, T]]]] = None,
        on_auth_error: Optional[Callable[[str], None]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RetryResult:
        """带重试的API调用执行器
        
        Args:
            func: API调用函数，返回 (success, message, data) 三元组
            on_rate_limit: 频率限制回调 (可选)
            on_token_error: Token错误回调，可返回fallback结果 (可选)
            on_auth_error: 认证错误回调 (可选)
            context: 上下文信息，用于日志记录 (可选)
            
        Returns:
            RetryResult: 执行结果
            
        Example:
            >>> result = handler.execute(
            ...     func=lambda: spider.get_note(note_id, cookie),
            ...     on_rate_limit=lambda: delay_manager.record_rate_limit(),
            ...     on_token_error=lambda: try_with_new_token(),
            ...     context={'note_id': note_id}
            ... )
        """
        ctx_str = f" [{context}]" if context else ""
        last_error_type = ErrorType.UNKNOWN
        last_message = ""
        
        for retry_attempt in range(self.max_retries):
            # 非首次重试需要等待
            if retry_attempt > 0:
                wait_time = self._get_wait_time(retry_attempt - 1, last_error_type)
                logger.debug(f"Retry {retry_attempt}/{self.max_retries}{ctx_str}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            
            try:
                success, msg, data = func()
                last_message = msg
                
                if success and data is not None:
                    # 成功
                    if self.use_adaptive_delay:
                        get_adaptive_delay_manager().record_success()
                    return RetryResult(
                        success=True,
                        error_type=None,
                        message=msg,
                        data=data,
                        retry_count=retry_attempt,
                    )
                
                # 分类错误
                error_type = self.classify_error(msg)
                last_error_type = error_type
                
                logger.debug(f"API call failed{ctx_str}: {msg} (type={error_type.value})")
                
                # 认证错误 - 立即返回，不重试
                if error_type == ErrorType.AUTH_ERROR:
                    if on_auth_error:
                        on_auth_error(msg)
                    return RetryResult(
                        success=False,
                        error_type=error_type,
                        message=msg,
                        retry_count=retry_attempt,
                    )
                
                # 频率限制 - 记录并重试
                if error_type == ErrorType.RATE_LIMITED:
                    if on_rate_limit:
                        on_rate_limit()
                    if self.use_adaptive_delay:
                        get_adaptive_delay_manager().record_rate_limit()
                    if self._should_retry(error_type, retry_attempt):
                        continue
                
                # Token错误 - 尝试fallback
                if error_type == ErrorType.TOKEN_ERROR:
                    if on_token_error:
                        fallback_result = on_token_error()
                        if fallback_result:
                            fb_success, fb_msg, fb_data = fallback_result
                            if fb_success and fb_data is not None:
                                return RetryResult(
                                    success=True,
                                    error_type=None,
                                    message=fb_msg,
                                    data=fb_data,
                                    retry_count=retry_attempt,
                                )
                    # Fallback失败，返回错误
                    return RetryResult(
                        success=False,
                        error_type=error_type,
                        message=msg,
                        retry_count=retry_attempt,
                    )
                
                # 资源不可用 - 立即返回，不重试
                if error_type == ErrorType.UNAVAILABLE:
                    return RetryResult(
                        success=False,
                        error_type=error_type,
                        message=msg,
                        retry_count=retry_attempt,
                    )
                
                # Items缺失 - 可以重试
                if error_type == ErrorType.ITEMS_MISSING:
                    logger.warning(f"Items missing{ctx_str}: {msg}")
                    if self._should_retry(error_type, retry_attempt):
                        continue
                
                # 其他错误 - 判断是否重试
                if self._should_retry(error_type, retry_attempt):
                    continue
                
            except Exception as e:
                last_message = str(e)
                error_type = self.classify_error(str(e))
                last_error_type = error_type
                logger.warning(f"Exception during API call{ctx_str}: {e}")
                
                if self._should_retry(error_type, retry_attempt):
                    continue
        
        # 所有重试都失败
        return RetryResult(
            success=False,
            error_type=last_error_type,
            message=last_message,
            retry_count=self.max_retries - 1,
        )
    
    def execute_simple(
        self,
        func: Callable[[], T],
        on_error: Optional[Callable[[Exception], None]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Optional[T]]:
        """简单重试执行器 (用于不返回三元组的函数)
        
        Args:
            func: 普通函数，直接返回数据或抛出异常
            on_error: 错误回调 (可选)
            context: 上下文信息 (可选)
            
        Returns:
            (success, message, data) 三元组
        """
        ctx_str = f" [{context}]" if context else ""
        
        for retry_attempt in range(self.max_retries):
            if retry_attempt > 0:
                wait_time = self._get_wait_time(retry_attempt - 1, ErrorType.UNKNOWN)
                time.sleep(wait_time)
            
            try:
                result = func()
                return True, "success", result
            except Exception as e:
                error_msg = str(e)
                error_type = self.classify_error(error_msg)
                
                logger.debug(f"Simple call failed{ctx_str}: {e} (type={error_type.value})")
                
                if on_error:
                    on_error(e)
                
                if not self._should_retry(error_type, retry_attempt):
                    return False, error_msg, None
        
        return False, "Max retries exceeded", None


# 便捷函数
def classify_api_error(msg: str) -> ErrorType:
    """分类API错误类型 (便捷函数)"""
    return ApiRetryHandler.classify_error(msg)


def is_rate_limit_error(msg: str) -> bool:
    """检查是否是频率限制错误 (便捷函数)"""
    return ApiRetryHandler.is_rate_limited(msg)


def is_auth_error(msg: str) -> bool:
    """检查是否是认证错误 (便捷函数)"""
    return ApiRetryHandler.is_auth_error(msg)


def is_token_error(msg: str) -> bool:
    """检查是否是Token错误 (便捷函数)"""
    return ApiRetryHandler.is_token_error(msg)


# 默认实例
_default_handler: Optional[ApiRetryHandler] = None
_handler_lock = None


def get_api_retry_handler() -> ApiRetryHandler:
    """获取默认的API重试处理器单例"""
    global _default_handler, _handler_lock
    
    import threading
    if _handler_lock is None:
        _handler_lock = threading.Lock()
    
    if _default_handler is None:
        with _handler_lock:
            if _default_handler is None:
                _default_handler = ApiRetryHandler()
                logger.info("[ApiRetryHandler] Default instance initialized")
    
    return _default_handler

