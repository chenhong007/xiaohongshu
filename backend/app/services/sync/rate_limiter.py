"""
全局 API 调用限流器

在 XHS_Apis 层面添加请求速率限制，提供统一的限流管理，而不是依赖各个模块自己管理延迟。

核心功能:
- 令牌桶算法实现平滑限流
- 全局请求速率控制
- 动态调整限流参数（根据限流响应）
- 请求队列管理
- 线程安全设计

使用示例:
    # 方式1: 直接使用限流器
    limiter = get_api_rate_limiter()
    limiter.acquire()  # 阻塞等待直到获取令牌
    result = xhs_apis.get_user_info(...)
    
    # 方式2: 使用带限流的 API 包装类
    rate_limited_apis = RateLimitedXHSApis(xhs_apis)
    result = rate_limited_apis.get_user_info(...)  # 自动限流
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps

from ...utils.logger import get_logger

logger = get_logger('rate_limiter')


@dataclass
class RateLimiterConfig:
    """限流器配置"""
    
    # 基础配置
    requests_per_second: float = 0.5  # 每秒请求数（0.5 = 每2秒1个请求）
    burst_size: int = 3  # 令牌桶大小（允许的突发请求数）
    
    # 动态调整配置
    min_interval: float = 1.0  # 最小请求间隔（秒）
    max_interval: float = 30.0  # 最大请求间隔（秒）
    
    # 限流响应后的惩罚
    rate_limit_penalty_multiplier: float = 2.0  # 限流后间隔倍数
    rate_limit_penalty_duration: float = 60.0  # 惩罚持续时间（秒）
    
    # 恢复配置
    success_recovery_threshold: int = 5  # 连续成功多少次后开始恢复
    recovery_factor: float = 0.9  # 恢复因子（每次恢复减少的比例）


@dataclass 
class RateLimiterStats:
    """限流器统计信息"""
    total_requests: int = 0
    total_waits: int = 0  # 需要等待的请求数
    total_wait_time: float = 0.0  # 累计等待时间
    rate_limit_hits: int = 0  # 触发限流的次数
    current_interval: float = 2.0  # 当前请求间隔
    last_request_time: float = 0.0
    consecutive_successes: int = 0


class TokenBucketRateLimiter:
    """令牌桶限流器
    
    使用令牌桶算法实现平滑的请求速率控制：
    - 令牌以固定速率生成（requests_per_second）
    - 每次请求消耗一个令牌
    - 桶满时多余的令牌被丢弃
    - 请求时如果没有令牌，需要等待
    
    特点：
    - 允许一定程度的突发请求（burst_size）
    - 长期来看保证平均请求速率
    - 动态调整（根据服务端响应）
    """
    
    def __init__(self, config: Optional[RateLimiterConfig] = None):
        """初始化限流器
        
        Args:
            config: 限流配置，不提供则使用默认配置
        """
        self._config = config or RateLimiterConfig()
        self._stats = RateLimiterStats(current_interval=1.0 / self._config.requests_per_second)
        
        # 令牌桶状态
        self._tokens = float(self._config.burst_size)  # 初始满桶
        self._last_token_time = time.time()
        
        # 动态调整状态
        self._current_rps = self._config.requests_per_second
        self._penalty_until = 0.0  # 惩罚结束时间
        
        # 线程安全
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        
        logger.info(
            f"[RateLimiter] 初始化: rps={self._config.requests_per_second}, "
            f"burst={self._config.burst_size}, interval={self._stats.current_interval:.1f}s"
        )
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取一个令牌（阻塞）
        
        Args:
            timeout: 最大等待时间（秒），None 表示无限等待
            
        Returns:
            True 如果成功获取令牌，False 如果超时
        """
        start_time = time.time()
        
        with self._condition:
            while True:
                # 补充令牌
                self._refill_tokens()
                
                # 检查是否在惩罚期
                current_time = time.time()
                if current_time < self._penalty_until:
                    wait_time = self._penalty_until - current_time
                    logger.debug(f"[RateLimiter] 在惩罚期，需等待 {wait_time:.1f}s")
                    if timeout is not None and wait_time > timeout:
                        return False
                    self._condition.wait(min(wait_time, timeout or wait_time))
                    continue
                
                # 尝试获取令牌
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._stats.total_requests += 1
                    self._stats.last_request_time = current_time
                    
                    elapsed = current_time - start_time
                    if elapsed > 0.01:  # 实际等待了
                        self._stats.total_waits += 1
                        self._stats.total_wait_time += elapsed
                        logger.debug(f"[RateLimiter] 获取令牌，等待了 {elapsed:.2f}s")
                    
                    return True
                
                # 计算需要等待的时间
                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self._current_rps
                
                # 检查超时
                if timeout is not None:
                    elapsed = current_time - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return False
                    wait_time = min(wait_time, remaining)
                
                logger.debug(f"[RateLimiter] 等待令牌，预计 {wait_time:.2f}s")
                self._condition.wait(wait_time)
    
    def try_acquire(self) -> bool:
        """尝试获取令牌（非阻塞）
        
        Returns:
            True 如果成功获取令牌
        """
        with self._lock:
            self._refill_tokens()
            
            current_time = time.time()
            if current_time < self._penalty_until:
                return False
            
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._stats.total_requests += 1
                self._stats.last_request_time = current_time
                return True
            
            return False
    
    def _refill_tokens(self) -> None:
        """补充令牌（内部方法，需要持有锁）"""
        current_time = time.time()
        elapsed = current_time - self._last_token_time
        
        if elapsed > 0:
            # 根据经过的时间补充令牌
            new_tokens = elapsed * self._current_rps
            self._tokens = min(self._tokens + new_tokens, float(self._config.burst_size))
            self._last_token_time = current_time
    
    def record_rate_limit(self) -> None:
        """记录一次限流响应
        
        调用此方法会触发惩罚机制，降低请求速率。
        """
        with self._lock:
            self._stats.rate_limit_hits += 1
            self._stats.consecutive_successes = 0
            
            # 降低请求速率
            old_rps = self._current_rps
            self._current_rps = max(
                self._current_rps / self._config.rate_limit_penalty_multiplier,
                1.0 / self._config.max_interval
            )
            
            # 设置惩罚期
            penalty_duration = self._config.rate_limit_penalty_duration * (
                1 + self._stats.rate_limit_hits * 0.5  # 累计惩罚
            )
            self._penalty_until = time.time() + penalty_duration
            
            self._stats.current_interval = 1.0 / self._current_rps
            
            logger.warning(
                f"[RateLimiter] 触发限流 #{self._stats.rate_limit_hits}: "
                f"rps {old_rps:.3f} -> {self._current_rps:.3f}, "
                f"惩罚 {penalty_duration:.0f}s"
            )
            
            # 唤醒等待的线程，让它们重新计算等待时间
            self._condition.notify_all()
    
    def record_success(self) -> None:
        """记录一次成功请求
        
        连续成功后会逐步恢复请求速率。
        """
        with self._lock:
            self._stats.consecutive_successes += 1
            
            # 检查是否可以恢复速率
            if self._stats.consecutive_successes >= self._config.success_recovery_threshold:
                max_rps = self._config.requests_per_second
                
                if self._current_rps < max_rps:
                    old_rps = self._current_rps
                    self._current_rps = min(
                        self._current_rps / self._config.recovery_factor,
                        max_rps
                    )
                    self._stats.current_interval = 1.0 / self._current_rps
                    self._stats.consecutive_successes = 0
                    
                    logger.info(
                        f"[RateLimiter] 速率恢复: rps {old_rps:.3f} -> {self._current_rps:.3f}"
                    )
    
    def reset(self) -> None:
        """重置限流器状态"""
        with self._lock:
            self._tokens = float(self._config.burst_size)
            self._last_token_time = time.time()
            self._current_rps = self._config.requests_per_second
            self._penalty_until = 0.0
            self._stats = RateLimiterStats(current_interval=1.0 / self._config.requests_per_second)
            logger.info("[RateLimiter] 已重置")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                'total_requests': self._stats.total_requests,
                'total_waits': self._stats.total_waits,
                'total_wait_time': round(self._stats.total_wait_time, 2),
                'rate_limit_hits': self._stats.rate_limit_hits,
                'current_interval': round(self._stats.current_interval, 2),
                'current_rps': round(self._current_rps, 3),
                'tokens_available': round(self._tokens, 2),
                'consecutive_successes': self._stats.consecutive_successes,
                'in_penalty': time.time() < self._penalty_until,
            }
    
    @property
    def current_interval(self) -> float:
        """当前请求间隔（秒）"""
        with self._lock:
            return 1.0 / self._current_rps


def rate_limited(limiter: 'TokenBucketRateLimiter'):
    """限流装饰器
    
    用于装饰需要限流的函数。
    
    Args:
        limiter: 限流器实例
        
    Example:
        limiter = TokenBucketRateLimiter()
        
        @rate_limited(limiter)
        def call_api():
            return api.get_data()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter.acquire()
            try:
                result = func(*args, **kwargs)
                limiter.record_success()
                return result
            except Exception as e:
                # 检查是否是限流错误
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['rate limit', '频率', '限制', '429']):
                    limiter.record_rate_limit()
                raise
        return wrapper
    return decorator


class RateLimitedXHSApis:
    """带限流的 XHS_Apis 包装类
    
    包装原始的 XHS_Apis 实例，在每次 API 调用前自动进行限流控制。
    
    使用示例:
        from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
        
        xhs_apis = XHS_Apis()
        rate_limited_apis = RateLimitedXHSApis(xhs_apis)
        
        # 自动限流的 API 调用
        success, msg, result = rate_limited_apis.get_user_info(user_id, cookies_str)
    
    特点:
    - 透明包装，API 签名与原始类完全一致
    - 自动识别限流响应并调整速率
    - 支持自定义限流配置
    - 提供统计信息查询
    """
    
    # 已知的限流错误关键词
    RATE_LIMIT_KEYWORDS = [
        'rate limit', '频率', '限制', '请求过于频繁', 
        '操作太频繁', 'too many requests', '429',
        '访问频率过高', '稍后再试'
    ]
    
    # 需要限流的 API 方法列表（不包括静态方法和工具方法）
    RATE_LIMITED_METHODS = [
        'get_homefeed_all_channel',
        'get_homefeed_recommend',
        'get_homefeed_recommend_by_num',
        'get_user_info',
        'get_user_self_info',
        'get_user_self_info2',
        'get_user_note_info',
        'get_user_all_notes',
        'get_user_like_note_info',
        'get_user_all_like_note_info',
        'get_user_collect_note_info',
        'get_user_all_collect_note_info',
        'get_note_info',
        'get_search_keyword',
        'search_note',
        'search_some_note',
        'search_user',
        'search_some_user',
        'get_note_out_comment',
        'get_note_all_out_comment',
        'get_note_inner_comment',
        'get_note_all_inner_comment',
        'get_note_all_comment',
        'get_unread_message',
        'get_metions',
        'get_all_metions',
        'get_likesAndcollects',
        'get_all_likesAndcollects',
        'get_new_connections',
        'get_all_new_connections',
    ]
    
    def __init__(
        self, 
        xhs_apis,
        config: Optional[RateLimiterConfig] = None,
        limiter: Optional[TokenBucketRateLimiter] = None
    ):
        """初始化带限流的 API 包装类
        
        Args:
            xhs_apis: 原始的 XHS_Apis 实例
            config: 限流配置（如果不提供 limiter）
            limiter: 自定义限流器（优先使用）
        """
        self._xhs_apis = xhs_apis
        self._limiter = limiter or get_api_rate_limiter(config)
        
        logger.info(f"[RateLimitedXHSApis] 已初始化，包装 {len(self.RATE_LIMITED_METHODS)} 个 API 方法")
    
    def __getattr__(self, name: str) -> Any:
        """动态代理 API 方法
        
        对于需要限流的方法，添加限流控制；
        对于其他方法，直接透传。
        """
        original_attr = getattr(self._xhs_apis, name)
        
        # 非方法属性直接返回
        if not callable(original_attr):
            return original_attr
        
        # 检查是否需要限流
        if name not in self.RATE_LIMITED_METHODS:
            return original_attr
        
        # 创建带限流的包装方法
        @wraps(original_attr)
        def rate_limited_method(*args, **kwargs) -> Tuple[bool, str, Any]:
            # 获取令牌
            self._limiter.acquire()
            
            try:
                # 调用原始方法
                result = original_attr(*args, **kwargs)
                
                # 检查结果是否表示限流
                if isinstance(result, tuple) and len(result) >= 2:
                    success, msg = result[0], result[1]
                    if not success and self._is_rate_limit_error(msg):
                        logger.warning(f"[RateLimitedXHSApis] API {name} 返回限流: {msg}")
                        self._limiter.record_rate_limit()
                    elif success:
                        self._limiter.record_success()
                
                return result
                
            except Exception as e:
                # 检查异常是否是限流
                if self._is_rate_limit_error(str(e)):
                    self._limiter.record_rate_limit()
                raise
        
        return rate_limited_method
    
    def _is_rate_limit_error(self, message: str) -> bool:
        """检查消息是否表示限流错误"""
        if not message:
            return False
        msg_lower = str(message).lower()
        return any(keyword in msg_lower for keyword in self.RATE_LIMIT_KEYWORDS)
    
    @property
    def limiter(self) -> TokenBucketRateLimiter:
        """获取限流器实例"""
        return self._limiter
    
    @property
    def original_apis(self):
        """获取原始的 XHS_Apis 实例"""
        return self._xhs_apis
    
    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """获取限流器统计信息"""
        return self._limiter.get_stats()


# 全局限流器实例
_global_rate_limiter: Optional[TokenBucketRateLimiter] = None
_global_rate_limiter_lock = threading.Lock()


def get_api_rate_limiter(config: Optional[RateLimiterConfig] = None) -> TokenBucketRateLimiter:
    """获取全局 API 限流器实例（单例模式）
    
    Args:
        config: 限流配置（仅首次调用时有效）
        
    Returns:
        全局限流器实例
        
    Note:
        默认配置为保守设置：
        - 每秒 0.5 个请求（每2秒1个）
        - 突发容量 3 个请求
        - 限流后惩罚 60 秒
    """
    global _global_rate_limiter
    
    with _global_rate_limiter_lock:
        if _global_rate_limiter is None:
            # 使用保守的默认配置
            default_config = config or RateLimiterConfig(
                requests_per_second=0.5,  # 每2秒1个请求
                burst_size=3,  # 允许3个突发请求
                min_interval=1.0,
                max_interval=30.0,
                rate_limit_penalty_multiplier=2.0,
                rate_limit_penalty_duration=60.0,
                success_recovery_threshold=5,
                recovery_factor=0.9,
            )
            _global_rate_limiter = TokenBucketRateLimiter(default_config)
        
        return _global_rate_limiter


def reset_api_rate_limiter() -> None:
    """重置全局限流器"""
    global _global_rate_limiter
    
    with _global_rate_limiter_lock:
        if _global_rate_limiter is not None:
            _global_rate_limiter.reset()
        _global_rate_limiter = None
        logger.info("[RateLimiter] 全局限流器已重置")


def create_rate_limited_xhs_apis(
    xhs_apis,
    config: Optional[RateLimiterConfig] = None
) -> RateLimitedXHSApis:
    """创建带限流的 XHS_Apis 实例
    
    便捷函数，创建使用全局限流器的包装实例。
    
    Args:
        xhs_apis: 原始的 XHS_Apis 实例
        config: 限流配置（可选）
        
    Returns:
        带限流的 API 包装实例
    """
    limiter = get_api_rate_limiter(config)
    return RateLimitedXHSApis(xhs_apis, limiter=limiter)

