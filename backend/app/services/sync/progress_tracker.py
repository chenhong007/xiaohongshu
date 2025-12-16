"""
Progress Tracker - Centralized progress tracking and heartbeat management

Provides unified progress tracking, heartbeat updates, and status broadcasting.
"""
from typing import Optional
from datetime import datetime

from ...models import Account
from ...extensions import db
from ...utils.logger import get_logger
from ..sync_log_broadcaster import sync_log_broadcaster

logger = get_logger('sync')


class ProgressTracker:
    """Tracks sync progress and manages heartbeat updates.
    
    Features:
    - Progress calculation and updates
    - Heartbeat management
    - Status broadcasting to frontend
    - Batch commit optimization
    """
    
    def __init__(
        self, 
        account: Account,
        total_notes: int,
        commit_interval: int = 5
    ):
        """Initialize progress tracker.
        
        Args:
            account: Account object to track
            total_notes: Total number of notes to process
            commit_interval: Commit to DB every N notes (default: 5)
        """
        self.account = account
        self.total_notes = total_notes
        self.commit_interval = commit_interval
        self.processed_count = 0
        self.new_notes_count = 0
        self._last_commit_index = 0
    
    def update(self, index: int, new_notes_count: Optional[int] = None) -> None:
        """Update progress and broadcast to frontend.
        
        Args:
            index: Current note index (0-based)
            new_notes_count: Optional count of new notes discovered
        """
        self.processed_count = index + 1
        if new_notes_count is not None:
            self.new_notes_count = new_notes_count
        
        # Update account fields
        self.account.loaded_msgs = self.processed_count
        self.account.progress = self._calculate_progress()
        
        # Commit and broadcast at intervals
        if self._should_commit(index):
            self._commit_and_broadcast()
    
    def finalize(self) -> None:
        """Finalize progress tracking (100% complete)."""
        self.account.loaded_msgs = self.total_notes
        self.account.progress = 100
        self._commit_and_broadcast()
    
    def _calculate_progress(self) -> int:
        """Calculate progress percentage."""
        if self.total_notes == 0:
            return 100
        return int((self.processed_count / self.total_notes) * 100)
    
    def _should_commit(self, index: int) -> bool:
        """Check if should commit at current index."""
        # Commit at intervals or at the end
        return (
            (index + 1) % self.commit_interval == 0 or
            index == self.total_notes - 1
        )
    
    def _commit_and_broadcast(self) -> None:
        """Commit to database and broadcast progress."""
        try:
            # Update heartbeat
            self.account.sync_heartbeat = datetime.utcnow()
            db.session.commit()
            
            # Broadcast to frontend
            sync_log_broadcaster.broadcast_progress(
                account_id=self.account.id,
                status='processing',
                progress=self.account.progress,
                loaded_msgs=self.account.loaded_msgs,
                total_msgs=self.total_notes,
                new_notes=self.new_notes_count
            )
        except Exception as e:
            logger.warning(f"[ProgressTracker] Failed to commit/broadcast: {e}")
            db.session.rollback()


class NoteProcessingHelper:
    """Helper for unified note processing in sync loop.
    
    Simplifies the decision logic for:
    - Should fetch detail?
    - Should update from list data?
    - How to save (new vs existing)?
    """
    
    @staticmethod
    def should_fetch_detail(
        sync_mode: str,
        existing_note,
        validator
    ) -> tuple[bool, list[str]]:
        """Determine if note detail should be fetched.
        
        Args:
            sync_mode: 'fast' or 'deep'
            existing_note: Existing Note object (or None for new notes)
            validator: NoteValidator instance
            
        Returns:
            Tuple of (should_fetch, reasons)
        """
        if sync_mode != 'deep':
            return False, []
        
        # New note in deep mode: always fetch detail
        if not existing_note:
            return True, ['new_note']
        
        # Existing note: check if needs sync
        needs_sync, reasons = validator.needs_deep_sync(existing_note)
        return needs_sync, reasons
    
    @staticmethod
    def process_quick_update(
        note_data: dict,
        existing_note,
        user_id: str,
        sync_mode: str
    ) -> dict:
        """Process quick update from list API data.
        
        Args:
            note_data: Raw note data from list API
            existing_note: Existing Note object (or None)
            user_id: User ID
            sync_mode: 'fast' or 'deep'
            
        Returns:
            Cleaned note data for saving
        """
        from .note_converter import NoteDataConverter
        
        # Convert list API data
        cleaned_data = NoteDataConverter.convert_from_list_api(
            note_data,
            user_id=user_id,
            existing_note=existing_note
        )
        
        return cleaned_data
    
    @staticmethod
    def should_save_immediately(sync_mode: str, existing_note) -> bool:
        """Check if note should be saved immediately (deep mode only).
        
        In deep mode, we save notes one by one.
        In fast mode, we batch save.
        
        Args:
            sync_mode: 'fast' or 'deep'
            existing_note: Existing Note object (or None)
            
        Returns:
            True if should save immediately
        """
        return sync_mode == 'deep'
    
    @staticmethod
    def update_existing_note_from_list(
        existing_note,
        cleaned_data: dict
    ) -> None:
        """Update existing note with list API data (fast update).
        
        Only updates like count and last_updated timestamp.
        
        Args:
            existing_note: Existing Note object
            cleaned_data: Cleaned data from list API
        """
        if cleaned_data.get('liked_count') is not None:
            existing_note.liked_count = cleaned_data['liked_count']
        existing_note.last_updated = datetime.utcnow()

