"""
Sync Module Tests

Tests for refactored sync service components.
"""
import pytest
import time
from unittest.mock import Mock, patch


class TestAdaptiveDelayManager:
    """Tests for AdaptiveDelayManager."""
    
    def test_initial_delay(self):
        """Test initial delay value."""
        from app.services.sync.delay_manager import AdaptiveDelayManager
        
        manager = AdaptiveDelayManager(initial_delay=10.0)
        
        # Delay should be around initial value with jitter
        delay = manager.get_delay()
        assert 8.0 <= delay <= 12.0
    
    def test_rate_limit_increases_delay(self):
        """Test that rate limit increases delay."""
        from app.services.sync.delay_manager import AdaptiveDelayManager
        
        manager = AdaptiveDelayManager(
            initial_delay=10.0,
            backoff_factor=2.0,
            max_delay=100.0
        )
        
        initial_stats = manager.get_stats()
        manager.record_rate_limit()
        after_stats = manager.get_stats()
        
        assert after_stats['current_delay'] > initial_stats['current_delay']
        assert after_stats['rate_limit_count'] == 1
    
    def test_success_recovery(self):
        """Test that consecutive successes reduce delay."""
        from app.services.sync.delay_manager import AdaptiveDelayManager
        
        manager = AdaptiveDelayManager(
            initial_delay=50.0,
            recovery_threshold=3,
            recovery_factor=0.5,
            min_delay=5.0
        )
        
        # Record rate limit to increase delay
        manager.record_rate_limit()
        high_delay = manager.get_stats()['current_delay']
        
        # Record enough successes to trigger recovery
        for _ in range(3):
            manager.record_success()
        
        recovered_delay = manager.get_stats()['current_delay']
        assert recovered_delay < high_delay
    
    def test_reset(self):
        """Test reset returns to initial state."""
        from app.services.sync.delay_manager import AdaptiveDelayManager
        
        manager = AdaptiveDelayManager(initial_delay=20.0)
        manager.record_rate_limit()
        manager.record_rate_limit()
        
        manager.reset()
        stats = manager.get_stats()
        
        assert stats['current_delay'] == 20.0
        assert stats['rate_limit_count'] == 0


class TestSyncLogCollector:
    """Tests for SyncLogCollector."""
    
    def test_add_issue(self):
        """Test adding issues."""
        from app.services.sync.log_collector import SyncLogCollector
        
        collector = SyncLogCollector(account_id=1, sync_mode='deep')
        collector.set_total(100)
        
        collector.add_issue(
            SyncLogCollector.TYPE_RATE_LIMITED,
            note_id='note123',
            message='Rate limited'
        )
        
        summary = collector.get_summary()
        assert summary['rate_limited'] == 1
        assert collector.get_issue_count() == 1
    
    def test_record_success(self):
        """Test recording success."""
        from app.services.sync.log_collector import SyncLogCollector
        
        collector = SyncLogCollector(account_id=1)
        collector.record_success()
        collector.record_success()
        
        summary = collector.get_summary()
        assert summary['success'] == 2
    
    def test_finalize(self):
        """Test finalizing logs."""
        from app.services.sync.log_collector import SyncLogCollector
        
        collector = SyncLogCollector(account_id=1, sync_mode='deep')
        collector.set_total(10)
        collector.record_success()
        collector.add_issue(SyncLogCollector.TYPE_FETCH_FAILED, note_id='n1')
        
        logs = collector.finalize()
        
        assert logs['sync_mode'] == 'deep'
        assert logs['start_time'] is not None
        assert logs['end_time'] is not None
        assert logs['summary']['total'] == 10
        assert logs['summary']['success'] == 1
        assert len(logs['issues']) == 1
    
    def test_has_problems(self):
        """Test problem detection."""
        from app.services.sync.log_collector import SyncLogCollector
        
        collector = SyncLogCollector(account_id=1)
        assert not collector.has_problems()
        
        collector.add_issue(SyncLogCollector.TYPE_RATE_LIMITED)
        assert collector.has_problems()


class TestRequestSessionPool:
    """Tests for RequestSessionPool."""
    
    def test_singleton(self):
        """Test singleton pattern."""
        from app.services.sync.session_pool import RequestSessionPool
        
        pool1 = RequestSessionPool()
        pool2 = RequestSessionPool()
        
        assert pool1 is pool2
    
    def test_get_stats(self):
        """Test getting statistics."""
        from app.services.sync.session_pool import get_request_session_pool
        
        pool = get_request_session_pool()
        stats = pool.get_stats()
        
        assert 'requests' in stats
        assert 'errors' in stats


class TestApiRetryHandler:
    """Tests for ApiRetryHandler."""
    
    def test_classify_rate_limit_error(self):
        """Test rate limit error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error('频次异常') == ErrorType.RATE_LIMITED
        assert ApiRetryHandler.classify_error('频繁操作') == ErrorType.RATE_LIMITED
        assert ApiRetryHandler.classify_error('请求过于频繁') == ErrorType.RATE_LIMITED
    
    def test_classify_auth_error(self):
        """Test auth error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error('未登录') == ErrorType.AUTH_ERROR
        assert ApiRetryHandler.classify_error('登录已过期') == ErrorType.AUTH_ERROR
        assert ApiRetryHandler.classify_error('需要登录') == ErrorType.AUTH_ERROR
        assert ApiRetryHandler.classify_error('凭据不合法') == ErrorType.AUTH_ERROR
        assert ApiRetryHandler.classify_error('10062') == ErrorType.AUTH_ERROR
    
    def test_classify_token_error(self):
        """Test token error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error('xsec_token invalid') == ErrorType.TOKEN_ERROR
        assert ApiRetryHandler.classify_error('签名错误') == ErrorType.TOKEN_ERROR
        assert ApiRetryHandler.classify_error('invalid signature') == ErrorType.TOKEN_ERROR
    
    def test_classify_unavailable_error(self):
        """Test unavailable error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error('暂时无法浏览') == ErrorType.UNAVAILABLE
        assert ApiRetryHandler.classify_error('笔记不存在') == ErrorType.UNAVAILABLE
        assert ApiRetryHandler.classify_error('已删除') == ErrorType.UNAVAILABLE
    
    def test_classify_items_missing_error(self):
        """Test items missing error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error("缺少'items'字段") == ErrorType.ITEMS_MISSING
        assert ApiRetryHandler.classify_error("KeyError: 'items'") == ErrorType.ITEMS_MISSING
    
    def test_classify_unknown_error(self):
        """Test unknown error classification."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        assert ApiRetryHandler.classify_error('some random error') == ErrorType.UNKNOWN
        assert ApiRetryHandler.classify_error('') == ErrorType.UNKNOWN
        assert ApiRetryHandler.classify_error(None) == ErrorType.UNKNOWN
    
    def test_execute_success(self):
        """Test successful execution."""
        from app.services.sync.retry_handler import ApiRetryHandler
        
        handler = ApiRetryHandler(max_retries=3, use_adaptive_delay=False)
        
        def success_func():
            return True, 'ok', {'data': 'test'}
        
        result = handler.execute(success_func)
        
        assert result.success is True
        assert result.data == {'data': 'test'}
        assert result.retry_count == 0
    
    def test_execute_with_retry(self):
        """Test execution with retry on transient error."""
        from app.services.sync.retry_handler import ApiRetryHandler
        
        handler = ApiRetryHandler(max_retries=3, base_wait=0.1, use_adaptive_delay=False)
        
        call_count = 0
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return False, 'some error', None
            return True, 'ok', {'data': 'recovered'}
        
        result = handler.execute(flaky_func)
        
        assert result.success is True
        assert result.data == {'data': 'recovered'}
        assert call_count == 2
    
    def test_execute_auth_error_no_retry(self):
        """Test that auth errors don't retry."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        handler = ApiRetryHandler(max_retries=3, use_adaptive_delay=False)
        
        call_count = 0
        def auth_fail_func():
            nonlocal call_count
            call_count += 1
            return False, '未登录', None
        
        result = handler.execute(auth_fail_func)
        
        assert result.success is False
        assert result.error_type == ErrorType.AUTH_ERROR
        assert call_count == 1  # No retry
    
    def test_execute_unavailable_no_retry(self):
        """Test that unavailable errors don't retry."""
        from app.services.sync.retry_handler import ApiRetryHandler, ErrorType
        
        handler = ApiRetryHandler(max_retries=3, use_adaptive_delay=False)
        
        call_count = 0
        def unavailable_func():
            nonlocal call_count
            call_count += 1
            return False, '笔记不存在', None
        
        result = handler.execute(unavailable_func)
        
        assert result.success is False
        assert result.error_type == ErrorType.UNAVAILABLE
        assert call_count == 1  # No retry
    
    def test_execute_rate_limit_callback(self):
        """Test rate limit callback is called."""
        from app.services.sync.retry_handler import ApiRetryHandler
        
        handler = ApiRetryHandler(max_retries=2, base_wait=0.1, use_adaptive_delay=False)
        
        rate_limit_called = False
        def on_rate_limit():
            nonlocal rate_limit_called
            rate_limit_called = True
        
        def rate_limit_func():
            return False, '频次异常', None
        
        result = handler.execute(rate_limit_func, on_rate_limit=on_rate_limit)
        
        assert rate_limit_called is True
        assert result.is_rate_limited is True
    
    def test_execute_token_error_with_fallback(self):
        """Test token error with successful fallback."""
        from app.services.sync.retry_handler import ApiRetryHandler
        
        handler = ApiRetryHandler(max_retries=3, use_adaptive_delay=False)
        
        def token_fail_func():
            return False, 'xsec_token invalid', None
        
        def token_fallback():
            return True, 'fallback ok', {'data': 'fallback_data'}
        
        result = handler.execute(token_fail_func, on_token_error=token_fallback)
        
        assert result.success is True
        assert result.data == {'data': 'fallback_data'}
    
    def test_retry_result_properties(self):
        """Test RetryResult helper properties."""
        from app.services.sync.retry_handler import RetryResult, ErrorType
        
        # Rate limited result
        rate_limited = RetryResult(False, ErrorType.RATE_LIMITED, 'rate limited')
        assert rate_limited.is_rate_limited is True
        assert rate_limited.is_recoverable is True
        
        # Auth error result
        auth_error = RetryResult(False, ErrorType.AUTH_ERROR, 'auth error')
        assert auth_error.is_auth_error is True
        assert auth_error.is_recoverable is False
        
        # Success result
        success = RetryResult(True, None, 'ok', data={'test': 1})
        assert success.is_rate_limited is False
        assert success.is_auth_error is False
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        from app.services.sync.retry_handler import (
            classify_api_error,
            is_rate_limit_error,
            is_auth_error,
            is_token_error,
            ErrorType,
        )
        
        assert classify_api_error('频次异常') == ErrorType.RATE_LIMITED
        assert is_rate_limit_error('频繁操作') is True
        assert is_auth_error('未登录') is True
        assert is_token_error('xsec invalid') is True
    
    def test_get_api_retry_handler_singleton(self):
        """Test singleton getter."""
        from app.services.sync.retry_handler import get_api_retry_handler
        
        handler1 = get_api_retry_handler()
        handler2 = get_api_retry_handler()
        
        assert handler1 is handler2
