"""
Sync Service Module - Modular sync functionality

This package contains refactored sync service components:
- delay_manager: Adaptive delay management for rate limiting
- session_pool: HTTP session pooling for connection reuse
- log_collector: Sync log collection and storage
- media_queue: Async media download queue
- note_validator: Note data completeness validation
- state_manager: Unified sync state management (status, heartbeat, progress)
- note_persistence: Note database persistence service
- token_manager: xsec_token unified management
- note_converter: Unified note data format conversion
"""
from .delay_manager import AdaptiveDelayManager, get_adaptive_delay_manager
from .session_pool import RequestSessionPool, get_request_session_pool
from .log_collector import SyncLogCollector
from .media_queue import MediaDownloadQueue, get_media_download_queue
from .note_validator import NoteValidator, DeepSyncValidator
from .state_manager import SyncStateManager, batch_mark_failed
from .note_persistence import NotePersistenceService
from .token_manager import XsecTokenManager, get_token_manager, reset_token_manager
from .note_converter import NoteDataConverter

__all__ = [
    'AdaptiveDelayManager',
    'get_adaptive_delay_manager',
    'RequestSessionPool',
    'get_request_session_pool',
    'SyncLogCollector',
    'MediaDownloadQueue',
    'get_media_download_queue',
    'NoteValidator',
    'DeepSyncValidator',
    'SyncStateManager',
    'batch_mark_failed',
    'NotePersistenceService',
    'XsecTokenManager',
    'get_token_manager',
    'reset_token_manager',
    'NoteDataConverter',
]
