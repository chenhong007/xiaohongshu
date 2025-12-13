"""
Sync Log Collector - Collect and store sync operation logs

This module provides structured logging for sync operations,
tracking issues like rate limits, missing fields, and failures.
"""
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger('log_collector')


class SyncLogCollector:
    """Sync log collector for tracking issues during deep sync.
    
    Collects various types of issues:
    - Rate limiting events
    - Unavailable notes
    - Missing fields (fallback to list data)
    - Fetch failures
    - Token refresh events
    - Media download failures
    - Authentication errors
    
    Example:
        >>> collector = SyncLogCollector(account_id=1, sync_mode='deep')
        >>> collector.set_total(100)
        >>> collector.add_issue(SyncLogCollector.TYPE_RATE_LIMITED, note_id='abc123')
        >>> collector.record_success()
        >>> logs = collector.finalize()
        >>> collector.save_to_db()
    """
    
    # Issue type constants
    TYPE_RATE_LIMITED = 'rate_limited'       # Rate limiting
    TYPE_UNAVAILABLE = 'unavailable'         # Note unavailable
    TYPE_MISSING_FIELD = 'missing_field'     # Missing fields (fallback to list data)
    TYPE_FETCH_FAILED = 'fetch_failed'       # Fetch failure
    TYPE_TOKEN_REFRESH = 'token_refresh'     # Token refresh event
    TYPE_MEDIA_FAILED = 'media_failed'       # Media download failure
    TYPE_AUTH_ERROR = 'auth_error'           # Authentication error
    
    # Maximum issues to store (prevent memory bloat)
    MAX_ISSUES = 500
    
    # Maximum message length
    MAX_MESSAGE_LENGTH = 500
    
    def __init__(self, account_id: int, sync_mode: str = 'deep'):
        """Initialize the log collector.
        
        Args:
            account_id: The account ID this collector is tracking
            sync_mode: Sync mode ('fast' or 'deep')
        """
        self.account_id = account_id
        self.sync_mode = sync_mode
        self.start_time = datetime.utcnow().isoformat() + 'Z'
        self.end_time: Optional[str] = None
        self.issues: List[Dict] = []
        self.summary = {
            'total': 0,           # Total notes
            'success': 0,         # Successfully processed
            'rate_limited': 0,    # Rate limit count
            'unavailable': 0,     # Unavailable notes
            'missing_field': 0,   # Missing fields (fallback)
            'fetch_failed': 0,    # Fetch failures
            'token_refresh': 0,   # Token refresh count
            'media_failed': 0,    # Media download failures
            'skipped': 0,         # Skipped (already complete)
        }
        self._lock = threading.Lock()
    
    def add_issue(
        self,
        issue_type: str,
        note_id: Optional[str] = None,
        message: Optional[str] = None,
        fields: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an issue record.
        
        Args:
            issue_type: Type of issue (use TYPE_* constants)
            note_id: Related note ID
            message: Error message (truncated to MAX_MESSAGE_LENGTH)
            fields: List of missing field names
            extra: Additional context data
        """
        with self._lock:
            issue = {
                'type': issue_type,
                'time': datetime.utcnow().isoformat() + 'Z',
            }
            if note_id:
                issue['note_id'] = note_id
            if message:
                issue['message'] = message[:self.MAX_MESSAGE_LENGTH]
            if fields:
                issue['fields'] = fields
            if extra:
                issue['extra'] = extra
            
            # Limit issue list size
            if len(self.issues) < self.MAX_ISSUES:
                self.issues.append(issue)
            
            # Update summary counts
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
    
    def record_success(self) -> None:
        """Record a successfully processed note."""
        with self._lock:
            self.summary['success'] += 1
    
    def record_skipped(self) -> None:
        """Record a skipped note (already has complete data)."""
        with self._lock:
            self.summary['skipped'] += 1
    
    def set_total(self, total: int) -> None:
        """Set the total note count.
        
        Args:
            total: Total number of notes to process
        """
        with self._lock:
            self.summary['total'] = total
    
    def finalize(self) -> Dict:
        """Finalize log collection and generate final log data.
        
        Returns:
            Dictionary containing sync_mode, times, summary, and issues
        """
        with self._lock:
            self.end_time = datetime.utcnow().isoformat() + 'Z'
            return {
                'sync_mode': self.sync_mode,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'summary': self.summary.copy(),
                'issues': self.issues.copy(),
            }
    
    def save_to_db(self) -> bool:
        """Save logs to database.
        
        Returns:
            True if save succeeded, False otherwise
        """
        try:
            # Import here to avoid circular imports
            from ....models import Account
            from ....extensions import db
            
            logs_data = self.finalize()
            account = Account.query.get(self.account_id)
            if account:
                account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                db.session.commit()
                logger.info(f"Sync logs saved for account {self.account_id}")
                return True
            else:
                logger.warning(f"Account {self.account_id} not found, cannot save logs")
                return False
        except Exception as e:
            logger.error(f"Failed to save sync logs: {e}")
            try:
                from ...extensions import db
                db.session.rollback()
            except Exception:
                pass
            return False
    
    def get_summary(self) -> Dict:
        """Get current summary statistics.
        
        Returns:
            Copy of the summary dictionary
        """
        with self._lock:
            return self.summary.copy()
    
    def get_issue_count(self) -> int:
        """Get total issue count.
        
        Returns:
            Number of issues recorded
        """
        with self._lock:
            return len(self.issues)
    
    def has_problems(self) -> bool:
        """Check if there are any problems recorded.
        
        Returns:
            True if any issues were recorded
        """
        with self._lock:
            return (
                self.summary['rate_limited'] > 0 or
                self.summary['missing_field'] > 0 or
                self.summary['fetch_failed'] > 0 or
                self.summary['unavailable'] > 0
            )
