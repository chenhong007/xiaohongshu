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
