"""
Sync Service - Core sync logic for note data synchronization

This module has been refactored to use modular components:
- sync.delay_manager: Adaptive delay management
- sync.session_pool: HTTP connection pooling
- sync.log_collector: Sync log collection
- sync.media_queue: Async media downloading
"""
import json
import os
import sys
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Optional, Set, Dict, Any, Tuple
from urllib.parse import urlparse

from flask import current_app

# Add Spider_XHS to sys.path for internal imports
_spider_xhs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'Spider_XHS')
if _spider_xhs_path not in sys.path:
    sys.path.insert(0, _spider_xhs_path)

from ..extensions import db
from ..models import Account, Note, Cookie
from ..utils.logger import get_logger
from ..config import Config
from .sync_log_broadcaster import sync_log_broadcaster

# Import refactored modules
from .sync.delay_manager import AdaptiveDelayManager, get_adaptive_delay_manager
from .sync.session_pool import RequestSessionPool, get_request_session_pool
from .sync.log_collector import SyncLogCollector
from .sync.media_queue import MediaDownloadQueue, get_media_download_queue
from .sync.note_validator import NoteValidator, DeepSyncValidator
from .sync.note_persistence import NotePersistenceService
from .sync.state_manager import SyncStateManager, batch_mark_failed
from .sync.token_manager import XsecTokenManager
from .sync.note_converter import NoteDataConverter
from .sync.note_fetcher import NoteFetcher, FetchResult
from .sync.retry_handler import ApiRetryHandler, ErrorType
from .sync.auth_handler import AuthErrorHandler, TokenRetryHelper
from .sync.progress_tracker import ProgressTracker, NoteProcessingHelper

# Spider_XHS imports
try:
    from Spider_XHS.xhs_utils.xhs_util import get_common_headers
    from Spider_XHS.xhs_utils.data_util import handle_note_info
    from Spider_XHS.main import Data_Spider
    from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
    SPIDER_AVAILABLE = True
except ImportError as e:
    SPIDER_AVAILABLE = False
    get_common_headers = None
    handle_note_info = None
    Data_Spider = None
    XHS_Apis = None

# Get logger
logger = get_logger('sync')


class SyncService:
    """Core sync service for synchronizing note data.
    
    Provides two sync modes:
    - fast: Quick sync using list API only, updates like counts
    - deep: Full sync with detail API, gets all fields including upload_time
    
    Features:
    - Heartbeat monitoring for stale task detection
    - Adaptive rate limiting with exponential backoff
    - Async media downloading
    - Comprehensive error handling and logging
    """
    
    _stop_event = threading.Event()
    _current_sync_mode: str = 'fast'
    _rate_limit_counter: int = 0
    _rate_limit_lock = threading.Lock()
    
    # Heartbeat timeout (seconds) - tasks without heartbeat are considered stale
    HEARTBEAT_TIMEOUT = 300  # 5 minutes
    
    # Maximum concurrent image downloads per note
    MAX_CONCURRENT_DOWNLOADS = 5
    
    # Preemptive token refresh interval (refresh token every N notes)
    TOKEN_REFRESH_INTERVAL = 50
    
    @staticmethod
    def _should_refresh_token(note_index: int) -> bool:
        """Check if xsec_token should be preemptively refreshed.
        
        Preemptively refresh token every TOKEN_REFRESH_INTERVAL notes
        to prevent token expiration during long sync sessions.
        
        Args:
            note_index: Current note index (0-based)
            
        Returns:
            True if token should be refreshed
        """
        return note_index > 0 and note_index % SyncService.TOKEN_REFRESH_INTERVAL == 0
    
    @staticmethod
    def _update_heartbeat(account_id: int) -> None:
        """Update account sync heartbeat time."""
        try:
            Account.query.filter_by(id=account_id).update(
                {'sync_heartbeat': datetime.utcnow()},
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update heartbeat (account_id={account_id}): {e}")
            db.session.rollback()
    
    @staticmethod
    def cleanup_stale_tasks(timeout_seconds: Optional[int] = None) -> int:
        """Clean up stale sync tasks.
        
        Detects tasks stuck in 'processing' state without heartbeat updates
        and marks them as failed.
        
        Args:
            timeout_seconds: Heartbeat timeout, defaults to HEARTBEAT_TIMEOUT
            
        Returns:
            Number of tasks cleaned up
        """
        if timeout_seconds is None:
            timeout_seconds = SyncService.HEARTBEAT_TIMEOUT
            
        try:
            cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
            
            # Find stale tasks: processing status with no/old heartbeat
            stale_accounts = Account.query.filter(
                Account.status == 'processing',
                db.or_(
                    Account.sync_heartbeat.is_(None),
                    Account.sync_heartbeat < cutoff_time
                )
            ).all()
            
            cleaned_count = 0
            for account in stale_accounts:
                heartbeat_info = ""
                if account.sync_heartbeat:
                    age = (datetime.utcnow() - account.sync_heartbeat).total_seconds()
                    heartbeat_info = f", last heartbeat: {int(age)}s ago"
                else:
                    heartbeat_info = ", no heartbeat record"
                
                logger.warning(
                    f"[StaleTaskCleanup] Account {account.name or account.user_id} (id={account.id}) "
                    f"status abnormal{heartbeat_info}, marking as failed"
                )
                
                SyncService._fail_single_account(
                    account,
                    "Sync task terminated abnormally (heartbeat timeout), please restart sync",
                    commit=False
                )
                cleaned_count += 1
            
            if cleaned_count > 0:
                db.session.commit()
                logger.info(f"[StaleTaskCleanup] Cleaned up {cleaned_count} stale tasks")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"[StaleTaskCleanup] Cleanup failed: {e}")
            db.session.rollback()
            return 0
    
    @staticmethod
    def _reset_rate_limit_counter() -> None:
        """Reset rate limit counter and adaptive delay manager."""
        with SyncService._rate_limit_lock:
            SyncService._rate_limit_counter = 0
        get_adaptive_delay_manager().reset()
    
    @staticmethod
    def _record_rate_limit() -> None:
        """Record a rate limit event, trigger exponential backoff."""
        with SyncService._rate_limit_lock:
            SyncService._rate_limit_counter += 1
            count = SyncService._rate_limit_counter
            logger.warning(f"[RateLimit] Cumulative count: {count}")
        
        delay_manager = get_adaptive_delay_manager()
        delay_manager.record_rate_limit()
        
        # Broadcast rate limit warning to frontend
        cooldown = delay_manager.get_rate_limit_wait()
        sync_log_broadcaster.broadcast_cookie_status(
            status='rate_limited',
            message=f'访问频次异常，已触发限流保护 (累计 {count} 次)',
            extra={
                'rate_limit_count': count,
                'cooldown_seconds': int(cooldown),
            }
        )
    
    @staticmethod
    def _record_success() -> None:
        """Record a successful request, trigger fast recovery."""
        with SyncService._rate_limit_lock:
            if SyncService._rate_limit_counter > 0:
                SyncService._rate_limit_counter = max(0, SyncService._rate_limit_counter - 1)
        get_adaptive_delay_manager().record_success()
    
    @staticmethod
    def _mark_accounts_failed(account_ids: Set[int], message: str) -> None:
        """Mark accounts as failed to prevent UI stuck in 'preparing' state.
        
        Note: This is a wrapper around batch_mark_failed for backward compatibility.
        """
        batch_mark_failed(account_ids, message)
    
    @staticmethod
    def _fail_accounts(account_ids: List[int], message: str, extra_fields: Optional[Dict[str, Any]] = None) -> None:
        """统一标记一批账号为失败状态."""
        if not account_ids:
            return
        
        update_data = {
            'status': SyncStateManager.STATUS_FAILED,
            'error_message': message,
            'sync_heartbeat': None
        }
        if extra_fields:
            update_data.update(extra_fields)
        
        try:
            Account.query.filter(Account.id.in_(account_ids)).update(
                update_data,
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to mark accounts {account_ids} as failed: {e}")
            db.session.rollback()
    
    @staticmethod
    def stop_sync() -> None:
        """Stop the current sync task."""
        logger.info("Stopping sync task...")
        SyncService._stop_event.set()

    @staticmethod
    def _is_media_missing(note: Note) -> bool:
        """Check if note media resources are missing."""
        if not note:
            return True
            
        try:
            # Check cover
            if not note.cover_local:
                return True
            cover_path = os.path.join(Config.MEDIA_PATH, os.path.basename(note.cover_local))
            if not os.path.exists(cover_path) or os.path.getsize(cover_path) < 1024:
                return True
                
            # Check note media directory
            note_dir = os.path.join(Config.MEDIA_PATH, str(note.note_id))
            if not os.path.exists(note_dir):
                return True
                
            # For image notes, check if images exist
            if note.type in ['图集', 'normal']:
                try:
                    img_list = json.loads(note.image_list) if note.image_list else []
                    if len(img_list) > 0:
                        files = [f for f in os.listdir(note_dir) 
                                if f.endswith('.jpg') and os.path.getsize(os.path.join(note_dir, f)) > 1024]
                        if len(files) == 0:
                            return True
                except Exception:
                    pass
                    
        except Exception as e:
            logger.warning(f"Error checking media for note {note.note_id}: {e}")
            return True
            
        return False

    @staticmethod
    def _get_missing_required_fields(note: Note, critical_only: bool = False) -> List[str]:
        """Get list of missing required fields for a note.
        
        In deep sync mode, if any of these fields are missing, we need to
        fetch detail page to refresh all data.
        
        IMPORTANT: List API (get_user_all_notes) does NOT return these fields:
        - upload_time: 发布时间 - 只有详情API返回
        - desc: 完整内容详情 - 列表API可能返回空或截断
        - image_list: 完整图片列表 - 列表API只有封面图
        - collected_count, comment_count, share_count: 可能缺失
        
        Args:
            note: Note object to check
            critical_only: If True, only return critical fields (upload_time, desc)
                          that definitely require detail API
        
        Returns:
            List of missing field names
        """
        if not note:
            return ['note']

        missing_fields = []

        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')

        # ===== CRITICAL FIELDS (only available from detail API) =====
        # upload_time: 发布时间 - 列表API永远不返回此字段！
        # 这是判断笔记数据是否完整的最重要指标
        if is_blank(getattr(note, 'upload_time', None)):
            missing_fields.append('upload_time')
        
        # desc: 内容详情 - 列表API可能返回空
        # 允许空字符串（用户确实没写描述），但不允许None
        if getattr(note, 'desc', None) is None:
            missing_fields.append('desc')
        
        if critical_only:
            return missing_fields
        
        # ===== BASIC FIELDS (usually available from list API) =====
        for field in ['note_id', 'user_id', 'nickname', 'avatar', 'title']:
            if is_blank(getattr(note, field, None)):
                missing_fields.append(field)

        # ===== INTERACTION FIELDS (may be missing from list API) =====
        # liked_count 通常列表API会返回
        if getattr(note, 'liked_count', None) is None:
            missing_fields.append('liked_count')
        # 这些字段列表API可能不返回
        if getattr(note, 'share_count', None) is None:
            missing_fields.append('share_count')
        if getattr(note, 'collected_count', None) is None:
            missing_fields.append('collected_count')
        if getattr(note, 'comment_count', None) is None:
            missing_fields.append('comment_count')

        # ===== MEDIA FIELDS =====
        # Cover fields
        for field in ['cover_remote', 'cover_local']:
            if is_blank(getattr(note, field, None)):
                missing_fields.append(field)

        # Media based on note type
        note_type = getattr(note, 'type', '')
        if note_type == '视频':
            if is_blank(getattr(note, 'video_addr', None)):
                missing_fields.append('video_addr')
        else:
            try:
                image_list = json.loads(note.image_list) if note.image_list else []
            except Exception:
                image_list = []
            # 列表API只返回封面图，所以图片列表<=1表示没有获取过详情
            if len(image_list) <= 1:
                missing_fields.append('image_list')

        # Local media files
        if SyncService._is_media_missing(note):
            missing_fields.append('local_media')

        return missing_fields
    
    @staticmethod
    def _get_fallback_missing_fields(existing_note: Optional[Note]) -> List[str]:
        """Get list of fields that will be missing when falling back to list API data.
        
        Used to log which fields are missing when detail API fails and we have to
        use list API data as fallback.
        
        Args:
            existing_note: Existing note from database (may be None for new notes)
            
        Returns:
            List of missing field names
        """
        missing_fields = []
        
        # upload_time: 列表API永远不返回此字段
        if not existing_note or not existing_note.upload_time:
            missing_fields.append('upload_time')
        # desc: 列表API可能返回空或截断的内容
        if not existing_note or not existing_note.desc:
            missing_fields.append('desc')
        # 互动数据: 列表API可能不返回所有计数
        if not existing_note or existing_note.collected_count is None:
            missing_fields.append('collected_count')
        if not existing_note or existing_note.comment_count is None:
            missing_fields.append('comment_count')
        if not existing_note or existing_note.share_count is None:
            missing_fields.append('share_count')
        
        return missing_fields
    
    @staticmethod
    def _is_note_data_complete(note: Note) -> bool:
        """Check if note has complete data from detail API.
        
        A note is considered complete if it has:
        - upload_time (only available from detail API)
        - desc (may be empty string, but not None)
        
        Returns:
            True if note data is complete
        """
        if not note:
            return False
        
        # upload_time is the key indicator - list API never returns it
        upload_time = getattr(note, 'upload_time', None)
        if upload_time is None or (isinstance(upload_time, str) and upload_time.strip() == ''):
            return False
        
        # desc should not be None (empty string is OK)
        if getattr(note, 'desc', None) is None:
            return False
        
        return True

    @staticmethod
    def _handle_auth_error(msg: str) -> bool:
        """Check if error is auth-related and mark Cookie as invalid.
        
        Note: This is a wrapper around AuthErrorHandler for backward compatibility.
        """
        is_auth, _ = AuthErrorHandler.handle_auth_error(msg)
        return is_auth

    @staticmethod
    def _is_xsec_token_error(msg: str) -> bool:
        """Check if error is xsec_token related.
        
        Note: This is a wrapper for backward compatibility.
        Prefer using XsecTokenManager.is_token_error() or ApiRetryHandler.is_token_error().
        """
        return XsecTokenManager.is_token_error(msg)

    @staticmethod
    def _sleep_with_jitter(sync_mode: str) -> None:
        """Sleep with adaptive delay for deep sync mode."""
        if sync_mode != 'deep':
            return
        
        delay_manager = get_adaptive_delay_manager()
        delay = delay_manager.get_delay()
        
        # Extra random pause (15% probability)
        if random.random() < 0.15:
            delay += random.uniform(5.0, 20.0)
        
        logger.debug(f"[AdaptiveDelay] Sleeping for {delay:.1f}s")
        time.sleep(delay)
    
    @staticmethod
    def _ensure_note_token(note_data: Dict[str, Any], note_token: Optional[str]) -> None:
        """确保列表API返回的笔记字典携带最新的xsec_token."""
        if note_token:
            note_data['xsec_token'] = note_token

    @staticmethod
    def check_cookie_valid() -> Tuple[bool, str]:
        """Check if current Cookie is valid.
        
        使用统一的 CookieService 进行验证（会自动处理无效 Cookie 的重新验证）
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        return CookieService.check_valid()
    
    @staticmethod
    def get_cookie_str() -> str:
        """Get valid decrypted Cookie string.
        
        使用统一的 CookieService 获取 Cookie（会自动处理无效 Cookie 的重新验证）
        """
        return CookieService.get_cookie_str()
    
    @staticmethod
    def start_sync(account_ids: List[int], sync_mode: str = 'fast') -> None:
        """Start background sync task.
        
        Args:
            account_ids: List of account IDs to sync
            sync_mode: 'fast' for quick sync, 'deep' for full sync
        """
        from .. import create_app
        app = create_app()
        
        SyncService._stop_event.clear()
        SyncService._current_sync_mode = sync_mode
        
        thread = threading.Thread(
            target=SyncService._run_sync, 
            args=(app, account_ids, sync_mode)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"Sync task started: {len(account_ids)} accounts, mode: {sync_mode}")
    
    @staticmethod
    def _run_sync(app, account_ids: List[int], sync_mode: str) -> None:
        """Execute sync in background thread with top-level error handling."""
        with app.app_context():
            try:
                SyncService._sync_accounts(account_ids, sync_mode)
            except Exception as e:
                logger.error(f"[FatalError] Sync thread crashed: {e}")
                try:
                    error_msg = f"Sync thread crashed: {str(e)[:200]}"
                    affected = Account.query.filter(
                        Account.id.in_(account_ids),
                        Account.status == 'processing'
                    ).update(
                        {
                            'status': 'failed',
                            'error_message': error_msg,
                            'sync_heartbeat': None
                        },
                        synchronize_session=False
                    )
                    db.session.commit()
                    logger.info(f"[FatalErrorRecovery] Marked {affected} accounts as failed")
                except Exception as inner_e:
                    logger.error(f"[FatalErrorRecovery] Failed to update account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _sync_accounts(account_ids: List[int], sync_mode: str) -> None:
        """Main sync logic for account notes."""
        if not SPIDER_AVAILABLE:
            logger.error("Spider_XHS module not available")
            SyncService._fail_accounts(account_ids, 'Spider module not available')
            return
            
        logger.info(f"Starting sync: {account_ids}, mode: {sync_mode}")
        
        SyncService._reset_rate_limit_counter()
        
        remaining_ids = set(account_ids)
        cookie_str = SyncService.get_cookie_str()
        if not cookie_str:
            logger.error("No valid Cookie found")
            SyncService._fail_accounts(account_ids, 'No valid Cookie, please login first')
            return
        
        try:
            xhs_apis = XHS_Apis()
            data_spider = Data_Spider()
        except Exception as e:
            error_msg = f"Failed to initialize API: {e}"
            logger.error(f"Failed to initialize XHS APIs: {e}")
            SyncService._fail_accounts(account_ids, error_msg)
            return
        
        # Create log collectors for all sync modes (to track sync type)
        sync_log_collectors = {}
        
        for acc_id in account_ids:
            if SyncService._stop_event.is_set():
                logger.info("Sync stopped by user")
                break
                
            # 为所有同步模式创建日志收集器，以便记录最近一次同步类型
            sync_log = SyncLogCollector(acc_id, sync_mode)
            sync_log_collectors[acc_id] = sync_log
            
            try:
                account = Account.query.get(acc_id)
                if not account:
                    continue
                
                remaining_ids.discard(acc_id)
                auth_error_msg = None
                account_name = account.name or account.user_id
                
                sync_log_broadcaster.info(
                    f"Starting sync: {account_name}",
                    account_id=acc_id,
                    account_name=account_name
                )
                
                # Update status
                account.status = 'processing'
                account.progress = 0
                account.loaded_msgs = 0
                account.error_message = None
                account.sync_heartbeat = datetime.utcnow()
                if sync_mode == 'deep':
                    account.sync_logs = None
                db.session.commit()
                
                # 使用 XsecTokenManager 统一管理 token
                token_mgr = XsecTokenManager(xhs_apis, cookie_str)
                warning_msg = None
                xsec_token = token_mgr.get_user_token(account.user_id)
                user_url = token_mgr.build_user_url(account.user_id, xsec_token)
                
                if not xsec_token:
                    warning_msg = "Failed to get user xsec_token, sync may fail"
                    logger.warning(f"Failed to fetch xsec_token for account {account.user_id}")
                    sync_log_broadcaster.warn(warning_msg, account_id=acc_id, account_name=account_name)
                    if sync_mode == 'deep':
                        error_msg = "Deep sync requires valid xsec_token, please re-login"
                        sync_log_broadcaster.error(error_msg, account_id=acc_id, account_name=account_name)
                        account.status = 'failed'
                        account.error_message = error_msg
                        db.session.commit()
                        continue
                
                # Get all notes with automatic token refresh on error
                def make_api_call():
                    nonlocal user_url, xsec_token
                    return xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                def on_token_refreshed(new_token):
                    nonlocal user_url, xsec_token
                    xsec_token = new_token
                    user_url = token_mgr.build_user_url(account.user_id, xsec_token)
                
                # First attempt with token refresh on error
                success, msg, all_note_info = TokenRetryHelper.retry_with_token_refresh(
                    api_call=make_api_call,
                    token_manager=token_mgr,
                    user_id=account.user_id,
                    should_refresh=lambda s, m: not s and sync_mode == 'deep' and XsecTokenManager.is_token_error(m),
                    on_token_refreshed=on_token_refreshed
                )
                
                # Retry if empty list (token might be stale)
                if success and not all_note_info:
                    logger.debug(f"Got 0 notes for {account.user_id}, refreshing token...")
                    success, msg, all_note_info = TokenRetryHelper.retry_with_token_refresh(
                        api_call=make_api_call,
                        token_manager=token_mgr,
                        user_id=account.user_id,
                        should_refresh=lambda s, m: s and not all_note_info,
                        on_token_refreshed=on_token_refreshed
                    )

                if not success:
                    # Use unified auth error handler
                    is_auth, auth_error_msg = AuthErrorHandler.handle_account_auth_error(
                        account=account,
                        msg=msg,
                        stop_callback=SyncService.stop_sync,
                        mark_failed_callback=SyncService._mark_accounts_failed,
                        remaining_account_ids=remaining_ids
                    )
                    
                    if not is_auth:
                        # Non-auth error
                        error_msg = f"Failed to get notes: {msg}"
                        if warning_msg:
                            error_msg = f"{warning_msg}. {error_msg}"
                        logger.warning(f"Failed to get notes for {account.user_id}: {msg}")
                        account.status = 'failed'
                        account.error_message = error_msg
                        db.session.commit()
                    
                    if auth_error_msg:
                        break
                    continue
                
                if success and not all_note_info:
                    error_msg = "Empty notes list, xsec_token may be invalid or user has no public notes"
                    if warning_msg:
                        error_msg = f"{warning_msg}. {error_msg}"
                    logger.warning(f"Empty notes for {account.user_id}")
                    account.status = 'failed'
                    account.error_message = error_msg
                    account.total_msgs = 0
                    account.loaded_msgs = 0
                    account.progress = 0
                    db.session.commit()
                    continue

                # Update user info
                try:
                    success_info, msg_info, user_info_res = xhs_apis.get_user_info(account.user_id, cookie_str)
                    
                    # Check for auth error
                    if not success_info:
                        is_auth, auth_error_msg = AuthErrorHandler.handle_account_auth_error(
                            account=account,
                            msg=msg_info,
                            stop_callback=SyncService.stop_sync,
                            mark_failed_callback=SyncService._mark_accounts_failed,
                            remaining_account_ids=remaining_ids
                        )
                        if is_auth:
                            break
                    
                    if success_info and user_info_res and user_info_res.get('data'):
                        user_data = user_info_res['data']
                        account.name = user_data.get('basic_info', {}).get('nickname') or account.name
                        account.avatar = user_data.get('basic_info', {}).get('images') or account.avatar
                        account.desc = user_data.get('basic_info', {}).get('desc') or account.desc
                        
                        for interaction in user_data.get('interactions', []):
                            if interaction.get('type') == 'fans':
                                account.fans = interaction.get('count')
                            elif interaction.get('type') == 'follows':
                                account.follows = interaction.get('count')
                            elif interaction.get('type') == 'interaction':
                                account.interaction = interaction.get('count')
                        
                        db.session.commit()
                except Exception as e:
                    logger.warning(f"Failed to update user info for {account.user_id}: {e}")
                
                # Pre-cache existing notes
                all_note_ids = [n.get('note_id') or n.get('id') for n in all_note_info]
                existing_notes_query = Note.query.filter(Note.note_id.in_(all_note_ids)).all()
                existing_notes_cache = {n.note_id: n for n in existing_notes_query}
                existing_note_ids_cache = set(existing_notes_cache.keys())
                logger.debug(f"[Cache] Pre-loaded {len(existing_note_ids_cache)}/{len(all_note_ids)} existing notes")
                
                # Filter notes for deep sync using NoteValidator
                # Pre-sync validation: identify which notes need to be fetched
                if sync_mode == 'deep':
                    # Create validator for this account
                    deep_validator = DeepSyncValidator(acc_id, account.user_id)
                    
                    # Get existing notes for validation
                    existing_notes_list = list(existing_notes_cache.values())
                    
                    # Run pre-sync validation
                    pre_validation_summary = deep_validator.pre_sync_validate(existing_notes_list)
                    if sync_log:
                        sync_log.set_pre_validation(pre_validation_summary)
                    
                    # Filter notes based on validation
                    filtered_notes = []
                    excluded_count = 0  # 排除的笔记数（不计入分母）
                    
                    for note in all_note_info:
                        note_id = note.get('note_id') or note.get('id')
                        existing_note = existing_notes_cache.get(note_id)
                        
                        # 新笔记：必须获取详情页数据
                        if not existing_note:
                            filtered_notes.append(note)
                            continue
                        
                        # 使用 NoteValidator 判断是否需要同步
                        needs_sync, reasons = NoteValidator.needs_deep_sync(existing_note)
                        
                        if needs_sync:
                            filtered_notes.append(note)
                            if reasons:
                                logger.debug(f"Note {note_id} needs sync: {', '.join(reasons)}")
                        else:
                            # 数据完整，不需要处理，不计入分母
                            excluded_count += 1
                            logger.debug(f"Note {note_id} is old (>7 days) and complete, excluding from sync")
                    
                    if excluded_count > 0:
                        logger.info(f"Excluded {excluded_count} old completed notes from deep sync (not counted in total)")
                        sync_log_broadcaster.info(
                            f"已排除 {excluded_count} 条数据完整的旧笔记",
                            account_id=acc_id,
                            account_name=account_name,
                            extra={'excluded_count': excluded_count}
                        )
                        all_note_info = filtered_notes

                total = len(all_note_info)
                account.total_msgs = total
                account.loaded_msgs = 0 
                db.session.commit()
                
                sync_log_broadcaster.info(
                    f"Got {total} notes",
                    account_id=acc_id,
                    account_name=account_name,
                    extra={'total': total}
                )
                
                if sync_log:
                    sync_log.set_total(total)
                
                # Initialize progress tracker
                progress_tracker = ProgressTracker(account, total, commit_interval=5)
                
                # Batch buffer for fast sync
                FAST_SYNC_BATCH_SIZE = 20
                fast_sync_batch = []
                
                for idx, simple_note in enumerate(all_note_info):
                    if SyncService._stop_event.is_set():
                        break

                    note_id = simple_note.get('note_id') or simple_note.get('id')
                    note_xsec_token = simple_note.get('xsec_token', '')
                    if not note_xsec_token:
                        logger.warning(f"Note {note_id} missing xsec_token")
                    SyncService._ensure_note_token(simple_note, note_xsec_token)
                    
                    # Determine if detail fetch is needed (using helper)
                    existing_note = existing_notes_cache.get(note_id)
                    need_fetch_detail, fetch_reasons = NoteProcessingHelper.should_fetch_detail(
                        sync_mode=sync_mode,
                        existing_note=existing_note,
                        validator=NoteValidator
                    )
                    
                    if need_fetch_detail and fetch_reasons:
                        logger.debug(f"Note {note_id} needs detail fetch: {', '.join(fetch_reasons)}")

                    if not need_fetch_detail:
                        # Quick update from list data (using helper)
                        try:
                            # Process quick update
                            cleaned_data = NoteProcessingHelper.process_quick_update(
                                note_data=simple_note,
                                existing_note=existing_note,
                                user_id=account.user_id,
                                sync_mode=sync_mode
                            )
                            
                            if sync_mode == 'deep':
                                if existing_note:
                                    # Update existing note with list data
                                    NoteProcessingHelper.update_existing_note_from_list(
                                        existing_note=existing_note,
                                        cleaned_data=cleaned_data
                                    )
                                    if sync_log:
                                        sync_log.record_skipped()
                                else:
                                    # New note: save with list data (incomplete but better than nothing)
                                    SyncService._save_note(cleaned_data, download_media=False, auto_commit=False)
                                    if sync_log:
                                        sync_log.record_success(note_id, is_new=True)
                            else:
                                # Fast sync: batch save
                                fast_sync_batch.append(cleaned_data)
                                
                                if len(fast_sync_batch) >= FAST_SYNC_BATCH_SIZE:
                                    try:
                                        inserted, updated = SyncService._bulk_save_notes(
                                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                                        )
                                        logger.debug(f"[FastSync] Batch saved {len(fast_sync_batch)}: {inserted} new, {updated} updated")
                                        # 记录新增笔记数量
                                        if sync_log and inserted > 0:
                                            sync_log.record_new_notes(inserted)
                                    except Exception as e:
                                        logger.error(f"[FastSync] Batch save failed: {e}")
                                    fast_sync_batch = []
                                
                        except Exception as e:
                            logger.warning(f"Error quick updating note {note_id}: {e}")
                    else:
                        # Fetch detail for deep sync using NoteFetcher
                        # 定义认证错误回调（用于处理 Cookie 失效）
                        def handle_auth_error_callback(msg: str):
                            nonlocal auth_error_msg
                            auth_error_msg = f"Cookie expired. Error: {msg}"
                            if sync_log:
                                sync_log.add_issue(
                                    SyncLogCollector.TYPE_AUTH_ERROR,
                                    note_id=note_id,
                                    message=str(msg)
                                )
                                sync_log.save_to_db()
                            SyncService.stop_sync()
                            account.status = 'failed'
                            account.error_message = auth_error_msg
                            db.session.commit()
                            SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                        
                        # 定义频率限制回调
                        def handle_rate_limit_callback():
                            SyncService._record_rate_limit()
                            sync_log_broadcaster.warn(
                                f"Rate limited",
                                account_id=acc_id,
                                account_name=account_name,
                                note_id=note_id
                            )
                        
                        # 使用 NoteFetcher 获取详情（统一的重试和 fallback 逻辑）
                        note_fetcher = NoteFetcher(
                            data_spider=data_spider,
                            token_manager=token_mgr,
                            cookie_str=cookie_str,
                            sync_log=sync_log,
                            on_auth_error=handle_auth_error_callback,
                            on_rate_limit=handle_rate_limit_callback
                        )
                        
                        fetch_result = note_fetcher.fetch_note_detail(
                            note_id=note_id,
                            note_token=note_xsec_token,
                            user_id=account.user_id
                        )
                        
                        detail_saved = False
                        
                        # 处理获取结果
                        if fetch_result.success and fetch_result.note_data:
                            try:
                                note_info = fetch_result.note_data
                                note_info['xsec_token'] = note_xsec_token
                                is_new_note = note_id not in existing_note_ids_cache
                                SyncService._save_note(note_info, download_media=True, auto_commit=False)
                                detail_saved = True
                                SyncService._record_success()
                                if sync_log:
                                    sync_log.record_success(note_id, is_new=is_new_note)
                            except Exception as e:
                                logger.warning(f"Error saving note {note_id}: {e}")
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_FETCH_FAILED,
                                        note_id=note_id,
                                        message=f"Save error: {str(e)}"
                                    )
                        elif fetch_result.is_auth_error:
                            # 认证错误已在回调中处理，跳出循环
                            break
                        
                        # Fallback to list data if detail fetch failed
                        if not detail_saved:
                            existing_note = existing_notes_cache.get(note_id)
                            missing_fields = SyncService._get_fallback_missing_fields(existing_note)
                            
                            if sync_log:
                                sync_log.add_issue(
                                    SyncLogCollector.TYPE_MISSING_FIELD,
                                    note_id=note_id,
                                    message=f"Fallback to list data (detail API failed), missing: {', '.join(missing_fields) if missing_fields else 'none'}",
                                    fields=missing_fields if missing_fields else []
                                )
                            
                            try:
                                cleaned_data = NoteDataConverter.convert_from_list_api(
                                    simple_note, 
                                    user_id=account.user_id,
                                    existing_note=existing_note
                                )
                                is_new_note = note_id not in existing_note_ids_cache
                                SyncService._save_note(cleaned_data, download_media=False, auto_commit=False)
                                logger.debug(f"Note {note_id} saved with list data (fallback), missing fields: {missing_fields}")
                                if sync_log:
                                    sync_log.record_success(note_id, is_new=is_new_note)
                            except Exception as e:
                                logger.warning(f"Error saving note {note_id} with list data: {e}")
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_FETCH_FAILED,
                                        note_id=note_id,
                                        message=f"Fallback save error: {str(e)}"
                                    )
                        
                        SyncService._sleep_with_jitter(sync_mode)
                    
                    # Update progress (using tracker)
                    new_notes_count = sync_log.get_new_notes_count() if sync_log else 0
                    progress_tracker.update(idx, new_notes_count)
                    
                # Save remaining batch
                if sync_mode == 'fast' and fast_sync_batch:
                    try:
                        inserted, updated = SyncService._bulk_save_notes(
                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                        )
                        logger.debug(f"[FastSync] Final batch: {inserted} new, {updated} updated")
                        # 记录新增笔记数量
                        if sync_log and inserted > 0:
                            sync_log.record_new_notes(inserted)
                    except Exception as e:
                        logger.error(f"[FastSync] Final batch save failed: {e}")
                
                # Complete sync
                if auth_error_msg:
                    if sync_log:
                        sync_log.save_to_db()
                    break
                    
                if not SyncService._stop_event.is_set():
                    account.status = 'completed'
                    account.progress = 100
                    account.loaded_msgs = total
                    account.last_sync = datetime.utcnow()
                    account.sync_heartbeat = None
                    
                    # Post-sync validation for deep sync
                    if sync_mode == 'deep' and 'deep_validator' in locals():
                        try:
                            # Re-fetch notes from database for validation
                            all_note_ids_for_validation = [n.get('note_id') or n.get('id') for n in all_note_info]
                            synced_notes = Note.query.filter(Note.note_id.in_(all_note_ids_for_validation)).all()
                            
                            # Run post-sync validation
                            post_validation_summary = deep_validator.post_sync_validate(synced_notes)
                            if sync_log:
                                sync_log.set_post_validation(post_validation_summary)
                            
                            # Log validation result
                            incomplete_count = post_validation_summary.get('incomplete_count', 0)
                            completeness_rate = post_validation_summary.get('completeness_rate', 100)
                            
                            if incomplete_count > 0:
                                sync_log_broadcaster.warn(
                                    f"同步完成，但有 {incomplete_count} 条笔记数据不完整 (完整率: {completeness_rate}%)",
                                    account_id=acc_id,
                                    account_name=account_name,
                                    extra={
                                        'incomplete_count': incomplete_count,
                                        'completeness_rate': completeness_rate,
                                    }
                                )
                            else:
                                sync_log_broadcaster.info(
                                    f"数据完整性验证通过 (完整率: {completeness_rate}%)",
                                    account_id=acc_id,
                                    account_name=account_name
                                )
                        except Exception as val_err:
                            logger.warning(f"Post-sync validation failed: {val_err}")
                    
                    if sync_log:
                        logs_data = sync_log.finalize()
                        account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                        
                        summary = logs_data.get('summary', {})
                        # 使用按笔记去重后的问题数（一个笔记多个问题只计1次）
                        issues_count = summary.get('unique_problem_notes', 0)
                        if issues_count > 0:
                            account.error_message = (
                                f"Sync completed with {issues_count} problem notes: "
                                f"rate_limited={summary.get('rate_limited', 0)}, "
                                f"missing={summary.get('missing_field', 0)}, "
                                f"failed={summary.get('fetch_failed', 0)}"
                            )
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed', summary)
                    else:
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed')
                else:
                    if account.status == 'processing':
                        mode_name = 'deep sync' if sync_mode == 'deep' else 'fast sync'
                        cancel_msg = account.error_message or f"User stopped {mode_name}"
                        SyncService._fail_single_account(account, cancel_msg, commit=False)
                        sync_log_broadcaster.broadcast_completed(acc_id, 'cancelled')
                    if sync_log:
                        sync_log.save_to_db()
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error syncing account {acc_id}: {e}")
                sync_log_broadcaster.error(
                    f"Sync error: {str(e)}",
                    account_id=acc_id,
                    account_name=locals().get('account_name')
                )
                db.session.rollback()
                try:
                    account = Account.query.get(acc_id)
                    if account:
                        error_msg = f"Sync error: {str(e)}"
                        extra_fields = None
                        if sync_log:
                            sync_log.add_issue(
                                SyncLogCollector.TYPE_FETCH_FAILED,
                                message=error_msg
                            )
                            logs_data = sync_log.finalize()
                            extra_fields = {'sync_logs': json.dumps(logs_data, ensure_ascii=False)}
                        SyncService._fail_single_account(account, error_msg, extra_fields=extra_fields)
                except Exception as inner_e:
                    logger.error(f"Error updating account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _submit_cover_download(cover_url: str, note_id: str) -> None:
        """统一封面下载提交逻辑，便于被批量/单条保存复用."""
        if not cover_url or not note_id:
            return
        queue = get_media_download_queue()
        queue.submit_cover_download(cover_url, note_id, callback=SyncService._update_cover_local)
    
    @staticmethod
    def _submit_media_download(note_id: str, data: Dict) -> None:
        """统一媒体下载提交逻辑，便于被复用."""
        if not note_id or not data:
            return
        queue = get_media_download_queue()
        queue.submit_media_download(note_id, data)
    
    @staticmethod
    def _bulk_save_notes(
        notes_data_list: List[Dict],
        existing_note_ids: Optional[Set[str]] = None,
        existing_notes_cache: Optional[Dict[str, Note]] = None
    ) -> Tuple[int, int]:
        """Bulk save notes to database.
        
        Delegates to NotePersistenceService for unified persistence logic.
        
        Args:
            notes_data_list: List of note data dictionaries
            existing_note_ids: Set of existing note IDs (deprecated, use existing_notes_cache)
            existing_notes_cache: Cache of existing Note objects
        
        Returns:
            Tuple of (inserted_count, updated_count)
        """
        return NotePersistenceService.bulk_save(
            notes_data=notes_data_list,
            existing_cache=existing_notes_cache,
            cover_callback=SyncService._submit_cover_download
        )
    
    @staticmethod
    def _save_note(note_data: Dict, download_media: bool = False, auto_commit: bool = True) -> None:
        """Save a single note to database.
        
        Delegates to NotePersistenceService for unified persistence logic.
        
        Args:
            note_data: Note data dictionary
            download_media: Whether to download media files
            auto_commit: Whether to auto-commit transaction
        """
        NotePersistenceService.save_single(
            note_data=note_data,
            download_media=download_media,
            auto_commit=auto_commit,
            cover_callback=SyncService._submit_cover_download,
            media_callback=SyncService._submit_media_download
        )
    
    @staticmethod
    def _update_cover_local(note_id: str, local_path: str) -> None:
        """Callback to update cover_local after async download."""
        if not local_path:
            return
        try:
            from flask import current_app
            try:
                app = current_app._get_current_object()
            except RuntimeError:
                return
            
            with app.app_context():
                Note.query.filter_by(note_id=note_id).update(
                    {'cover_local': local_path},
                    synchronize_session=False
                )
                db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update cover_local for {note_id}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass

    @staticmethod
    def _download_cover(remote_url: str, note_id: str) -> Optional[str]:
        """Download cover image (legacy method, prefer async queue)."""
        if not remote_url:
            return None
        try:
            Config.init_paths()
            parsed = urlparse(remote_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filename = f"{note_id}_cover{ext}"
            filepath = os.path.join(Config.MEDIA_PATH, filename)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                return f"/api/media/{filename}"
            
            headers = get_common_headers() if get_common_headers else {}
            session_pool = get_request_session_pool()
            
            for attempt in range(3):
                try:
                    resp = session_pool.get(remote_url, headers=headers, stream=True, timeout=15)
                    if resp.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        return f"/api/media/{filename}"
                    elif resp.status_code == 403:
                        time.sleep(1)
                except Exception as dl_err:
                    logger.warning(f"Download attempt {attempt+1} failed: {dl_err}")
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Download cover error for {note_id}: {e}")
        return None
