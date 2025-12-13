"""
Adaptive Delay Manager - Intelligent rate limiting with exponential backoff

This module provides smart delay management for API requests to avoid rate limiting.
Uses exponential backoff on failures and fast recovery on consecutive successes.
"""
import random
import threading
from typing import Dict

from ...utils.logger import get_logger

logger = get_logger('delay_manager')


class AdaptiveDelayManager:
    """Intelligent delay manager with exponential backoff and fast recovery.
    
    Core strategies:
    1. Exponential backoff: Double delay on each rate limit (up to max_delay)
    2. Fast recovery: Halve delay after N consecutive successes (down to min_delay)
    3. Dynamic adjustment: Automatically adjust base delay based on rate limit frequency
    
    Example:
        >>> manager = AdaptiveDelayManager(min_delay=5.0, max_delay=300.0)
        >>> delay = manager.get_delay()  # Get current delay with jitter
        >>> manager.record_rate_limit()  # On rate limit, increase delay
        >>> manager.record_success()     # On success, potentially decrease delay
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
        """Initialize the delay manager.
        
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
    
    def record_rate_limit(self) -> None:
        """Record a rate limit event, increase delay exponentially."""
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
    
    def record_success(self) -> None:
        """Record a successful request, potentially reduce delay."""
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
        """Get current delay with random jitter (±20%).
        
        Returns:
            Delay in seconds with jitter applied
        """
        with self._lock:
            jitter = random.uniform(0.8, 1.2)
            return self._current_delay * jitter
    
    def get_rate_limit_wait(self) -> float:
        """Get wait time after rate limit (longer than normal delay).
        
        Returns:
            Extended wait time in seconds for rate limit recovery
        """
        with self._lock:
            # Extra wait time based on consecutive rate limits
            base_wait = self._current_delay * 2
            extra_wait = min(self._rate_limit_count * 15, 120)
            return base_wait + extra_wait + random.uniform(5, 15)
    
    def reset(self) -> None:
        """Reset to initial state."""
        with self._lock:
            self._current_delay = self.initial_delay
            self._consecutive_success = 0
            self._rate_limit_count = 0
            logger.info("[AdaptiveDelay] Reset to initial state")
    
    def get_stats(self) -> Dict:
        """Get current statistics.
        
        Returns:
            Dictionary with current delay, consecutive success count, and rate limit count
        """
        with self._lock:
            return {
                'current_delay': self._current_delay,
                'consecutive_success': self._consecutive_success,
                'rate_limit_count': self._rate_limit_count,
            }


# Global singleton instance
_adaptive_delay_manager: AdaptiveDelayManager = None


def get_adaptive_delay_manager() -> AdaptiveDelayManager:
    """Get global adaptive delay manager instance (singleton pattern).
    
    Returns:
        The global AdaptiveDelayManager instance
    """
    global _adaptive_delay_manager
    if _adaptive_delay_manager is None:
        _adaptive_delay_manager = AdaptiveDelayManager()
    return _adaptive_delay_manager
