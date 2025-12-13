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
                
                account.status = 'failed'
                account.error_message = "Sync task terminated abnormally (heartbeat timeout), please restart sync"
                account.sync_heartbeat = None
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
    def _parse_count(value) -> int:
        """Parse count value that may be a string like '10.1万' to integer.
        
        Args:
            value: Count value, can be int, str like '10.1万', '1.2亿', or None
            
        Returns:
            Integer count value
        """
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
            try:
                # Try direct conversion first
                return int(value)
            except ValueError:
                pass
            try:
                # Handle Chinese units: 万 (10000), 亿 (100000000)
                if '亿' in value:
                    num = float(value.replace('亿', ''))
                    return int(num * 100000000)
                elif '万' in value:
                    num = float(value.replace('万', ''))
                    return int(num * 10000)
                else:
                    return int(float(value))
            except (ValueError, TypeError):
                return 0
        return 0
    
    @staticmethod
    def _convert_list_note(simple_note: Dict, user_id: str = None) -> Dict:
        """Convert list API note data to save format.
        
        List API returns different structure than detail API.
        This function converts list data to the format expected by _save_note.
        
        Args:
            simple_note: Note data from list API (get_user_all_notes)
            user_id: User ID to use if not in note data
            
        Returns:
            Dict in format expected by _save_note
        """
        note_id = simple_note.get('note_id') or simple_note.get('id') or ''
        
        # Extract user info from nested structure or flat structure
        user_info = simple_note.get('user') or {}
        note_user_id = user_info.get('user_id') or simple_note.get('user_id') or user_id or ''
        nickname = user_info.get('nickname') or simple_note.get('nickname') or ''
        avatar = user_info.get('avatar') or simple_note.get('avatar') or ''
        
        # Title can be in different fields
        title = simple_note.get('display_title') or simple_note.get('title') or ''
        if not title or title.strip() == '':
            title = '无标题'
        
        # Note type
        note_type = simple_note.get('type') or 'normal'
        if note_type == 'normal':
            note_type = '图集'
        elif note_type == 'video':
            note_type = '视频'
        
        # Interact info - can be nested or flat, parse string counts like "10.1万"
        interact_info = simple_note.get('interact_info') or {}
        liked_count = SyncService._parse_count(interact_info.get('liked_count') or simple_note.get('liked_count'))
        collected_count = SyncService._parse_count(interact_info.get('collected_count') or simple_note.get('collected_count'))
        comment_count = SyncService._parse_count(interact_info.get('comment_count') or simple_note.get('comment_count'))
        share_count = SyncService._parse_count(interact_info.get('share_count') or simple_note.get('share_count'))
        
        # Cover image
        cover_info = simple_note.get('cover') or {}
        cover_url = ''
        if isinstance(cover_info, dict):
            info_list = cover_info.get('info_list') or cover_info.get('url_default') or []
            if isinstance(info_list, list) and len(info_list) > 0:
                # Try to get higher quality image
                cover_url = info_list[-1].get('url') if isinstance(info_list[-1], dict) else str(info_list[-1])
            elif isinstance(info_list, str):
                cover_url = info_list
            # Fallback to url field
            if not cover_url:
                cover_url = cover_info.get('url') or cover_info.get('url_default') or ''
        elif isinstance(cover_info, str):
            cover_url = cover_info
        
        # Build note URL
        xsec_token = simple_note.get('xsec_token') or ''
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if xsec_token:
            note_url = f"{note_url}?xsec_token={xsec_token}&xsec_source=pc_search"
        
        return {
            'note_id': note_id,
            'note_url': note_url,
            'note_type': note_type,
            'user_id': note_user_id,
            'nickname': nickname,
            'avatar': avatar,
            'title': title,
            'desc': simple_note.get('desc') or '',
            'liked_count': liked_count,
            'collected_count': collected_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'video_cover': cover_url if note_type == '视频' else None,
            'video_addr': simple_note.get('video_addr') or None,
            'image_list': [cover_url] if cover_url else [],
            'tags': simple_note.get('tags') or [],
            'upload_time': simple_note.get('upload_time') or None,
            'ip_location': simple_note.get('ip_location') or '',
            'cover_remote': cover_url,
            'xsec_token': xsec_token,
        }
    
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
            logger.warning(f"[RateLimit] Cumulative count: {SyncService._rate_limit_counter}")
        get_adaptive_delay_manager().record_rate_limit()
    
    @staticmethod
    def _record_success() -> None:
        """Record a successful request, trigger fast recovery."""
        with SyncService._rate_limit_lock:
            if SyncService._rate_limit_counter > 0:
                SyncService._rate_limit_counter = max(0, SyncService._rate_limit_counter - 1)
        get_adaptive_delay_manager().record_success()
    
    @staticmethod
    def _mark_accounts_failed(account_ids: Set[int], message: str) -> None:
        """Mark accounts as failed to prevent UI stuck in 'preparing' state."""
        if not account_ids:
            return
        try:
            Account.query.filter(Account.id.in_(list(account_ids))).update(
                {
                    'status': 'failed',
                    'error_message': message,
                    'progress': 0
                },
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to batch mark accounts as failed: {e}")
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
    def _get_missing_required_fields(note: Note) -> List[str]:
        """Get list of missing required fields for a note.
        
        In deep sync mode, if any of these fields are missing, we need to
        fetch detail page to refresh all data.
        """
        if not note:
            return ['note']

        missing_fields = []

        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')

        # Basic text fields
        for field in ['note_id', 'user_id', 'nickname', 'avatar', 'title']:
            if is_blank(getattr(note, field, None)):
                missing_fields.append(field)

        # Desc allows empty string but not None
        if getattr(note, 'desc', None) is None:
            missing_fields.append('desc')

        # Upload time required for sorting/display
        if is_blank(getattr(note, 'upload_time', None)):
            missing_fields.append('upload_time')

        # Interaction fields - None means not fetched
        if getattr(note, 'liked_count', None) is None:
            missing_fields.append('liked_count')
        if getattr(note, 'share_count', None) is None:
            missing_fields.append('share_count')
        if getattr(note, 'collected_count', None) is None:
            missing_fields.append('collected_count')
        if getattr(note, 'comment_count', None) is None:
            missing_fields.append('comment_count')

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
            if len(image_list) <= 1:
                missing_fields.append('image_list')

        # Local media files
        if SyncService._is_media_missing(note):
            missing_fields.append('local_media')

        return missing_fields

    @staticmethod
    def _handle_auth_error(msg: str) -> bool:
        """Check if error is auth-related and mark Cookie as invalid."""
        auth_errors = ['未登录', '登录已过期', '需要登录', '401', '403', 'Unauthorized', '凭据不合法', '凭据无效', '10062']
        if any(error in str(msg) for error in auth_errors):
            logger.warning(f"Detected auth error: {msg}, marking Cookie as invalid...")
            try:
                cookie = Cookie.query.filter_by(is_active=True).first()
                if cookie:
                    cookie.stop_run_timer()
                    cookie.is_valid = False
                    cookie.last_checked = datetime.utcnow()
                    db.session.commit()
                    logger.info("Cookie marked as invalid")
                return True
            except Exception as e:
                logger.error(f"Error marking Cookie as invalid: {e}")
        return False

    @staticmethod
    def _is_xsec_token_error(msg: str) -> bool:
        """Check if error is xsec_token related."""
        if not msg:
            return False
        tokens = ['xsec', '签名', 'token', '参数错误', 'invalid signature']
        msg_lower = str(msg).lower()
        return any(keyword in msg_lower for keyword in tokens)

    @staticmethod
    def _fetch_user_xsec_token(user_id: str, xhs_apis, cookie_str: str) -> str:
        """Dynamically fetch user's xsec_token via search."""
        if not user_id or not SPIDER_AVAILABLE:
            return ''
        try:
            # Get user info for nickname
            success_info, msg_info, user_info = xhs_apis.get_user_info(user_id, cookie_str)
            if not success_info or not user_info:
                logger.debug(f"Failed to get user info for {user_id}: {msg_info}")
                return ''
            
            basic_info = user_info.get('data', {}).get('basic_info', {})
            nickname = basic_info.get('nickname', '')
            
            if not nickname:
                logger.debug(f"No nickname found for user {user_id}")
                return ''
            
            # Search user by nickname to get xsec_token
            success_search, msg_search, search_res = xhs_apis.search_user(nickname, cookie_str, page=1)
            if not success_search or not search_res:
                logger.debug(f"Failed to search user '{nickname}': {msg_search}")
                return ''
            
            # Match user_id in search results
            users = search_res.get('data', {}).get('users', [])
            for user in users:
                found_user_id = (user.get('user_id') or user.get('id') or 
                                user.get('userid') or user.get('userId'))
                if found_user_id == user_id:
                    xsec_token = user.get('xsec_token', '')
                    if xsec_token:
                        logger.debug(f"Fetched xsec_token for user {user_id} via search")
                        return xsec_token
            
            logger.debug(f"User {user_id} not found in search results")
        except Exception as e:
            logger.debug(f"Exception fetching xsec_token for user {user_id}: {e}")
        return ''

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
    def get_cookie_str() -> str:
        """Get valid decrypted Cookie string."""
        cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
        if cookie:
            return cookie.get_cookie_str()
        
        return getattr(Config, 'XHS_COOKIES', '')
    
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
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': 'Spider module not available'},
                synchronize_session=False
            )
            db.session.commit()
            return
            
        logger.info(f"Starting sync: {account_ids}, mode: {sync_mode}")
        
        SyncService._reset_rate_limit_counter()
        
        remaining_ids = set(account_ids)
        cookie_str = SyncService.get_cookie_str()
        if not cookie_str:
            logger.error("No valid Cookie found")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': 'No valid Cookie, please login first'},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        try:
            xhs_apis = XHS_Apis()
            data_spider = Data_Spider()
        except Exception as e:
            error_msg = f"Failed to initialize API: {e}"
            logger.error(f"Failed to initialize XHS APIs: {e}")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': error_msg},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        # Create log collectors for deep sync
        sync_log_collectors = {}
        
        for acc_id in account_ids:
            if SyncService._stop_event.is_set():
                logger.info("Sync stopped by user")
                break
                
            sync_log = None
            if sync_mode == 'deep':
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
                
                # Get user xsec_token
                warning_msg = None
                xsec_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                
                if xsec_token:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                else:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}'
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
                
                # Get all notes
                success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                # Retry with refreshed token if needed
                if not success and sync_mode == 'deep' and SyncService._is_xsec_token_error(msg):
                    new_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                    if new_token and new_token != xsec_token:
                        xsec_token = new_token
                        user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                        success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                # Retry if empty list
                if success and not all_note_info:
                    logger.debug(f"Got 0 notes for {account.user_id}, refreshing token...")
                    new_token = SyncService._fetch_user_xsec_token(account.user_id, xhs_apis, cookie_str)
                    if new_token and new_token != xsec_token:
                        xsec_token = new_token
                        user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                        success_retry, msg_retry, all_note_info_retry = xhs_apis.get_user_all_notes(user_url, cookie_str)
                        if success_retry and all_note_info_retry:
                            success, msg, all_note_info = success_retry, msg_retry, all_note_info_retry

                if not success:
                    if SyncService._handle_auth_error(msg):
                        error_msg = f"Cookie expired, please re-login. Error: {msg}"
                        auth_error_msg = error_msg
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, error_msg)
                    else:
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
                    
                    if not success_info and SyncService._handle_auth_error(msg_info):
                        auth_error_msg = f"Cookie expired. Error: {msg_info}"
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                    
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
                
                # Pre-cache existing notes
                all_note_ids = [n.get('note_id') or n.get('id') for n in all_note_info]
                existing_notes_query = Note.query.filter(Note.note_id.in_(all_note_ids)).all()
                existing_notes_cache = {n.note_id: n for n in existing_notes_query}
                existing_note_ids_cache = set(existing_notes_cache.keys())
                logger.debug(f"[Cache] Pre-loaded {len(existing_note_ids_cache)}/{len(all_note_ids)} existing notes")
                
                # Batch buffer for fast sync
                FAST_SYNC_BATCH_SIZE = 20
                fast_sync_batch = []
                
                for idx, simple_note in enumerate(all_note_info):
                    if SyncService._stop_event.is_set():
                        break

                    note_id = simple_note.get('note_id') or simple_note.get('id')
                    note_xsec_token = simple_note.get('xsec_token', '')
                    if note_xsec_token:
                        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_xsec_token}&xsec_source=pc_search"
                    else:
                        logger.warning(f"Note {note_id} missing xsec_token")
                        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                    
                    need_fetch_detail = False
                    
                    if sync_mode == 'deep':
                        existing_note = existing_notes_cache.get(note_id)
                        if not existing_note:
                            need_fetch_detail = True
                        else:
                            missing_fields = SyncService._get_missing_required_fields(existing_note)
                            if missing_fields:
                                need_fetch_detail = True
                                logger.debug(f"Note {note_id} missing fields: {missing_fields}")

                    if not need_fetch_detail:
                        # Quick update from list data
                        try:
                            if note_xsec_token:
                                simple_note['xsec_token'] = note_xsec_token
                            # Use list note converter instead of handle_note_info (which expects detail format)
                            cleaned_data = SyncService._convert_list_note(simple_note, user_id=account.user_id)
                            
                            if sync_mode == 'deep':
                                existing_note = existing_notes_cache.get(note_id)
                                if existing_note:
                                    if cleaned_data['liked_count'] is not None:
                                        existing_note.liked_count = cleaned_data['liked_count']
                                    existing_note.last_updated = datetime.utcnow()
                                    if sync_log:
                                        sync_log.record_skipped()
                            else:
                                fast_sync_batch.append(cleaned_data)
                                
                                if len(fast_sync_batch) >= FAST_SYNC_BATCH_SIZE:
                                    try:
                                        inserted, updated = SyncService._bulk_save_notes(
                                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                                        )
                                        logger.debug(f"[FastSync] Batch saved {len(fast_sync_batch)}: {inserted} new, {updated} updated")
                                    except Exception as e:
                                        logger.error(f"[FastSync] Batch save failed: {e}")
                                    fast_sync_batch = []
                                
                        except Exception as e:
                            logger.warning(f"Error quick updating note {note_id}: {e}")
                    else:
                        # Fetch detail for deep sync
                        detail_saved = False
                        rate_limited = False
                        last_error_msg = None
                        
                        for retry_attempt in range(3):
                            if retry_attempt > 0:
                                wait_time = random.uniform(3, 6) * retry_attempt
                                time.sleep(wait_time)
                            
                            success, msg, note_info = data_spider.spider_note(note_url, cookie_str)
                            last_error_msg = msg
                            
                            is_rate_limited = '频次异常' in str(msg) or '频繁操作' in str(msg)
                            is_unavailable = '暂时无法浏览' in str(msg) or '笔记不存在' in str(msg)
                            
                            if is_rate_limited:
                                rate_limited = True
                                SyncService._record_rate_limit()
                                sync_log_broadcaster.warn(
                                    f"Rate limited, retrying ({retry_attempt + 1}/3)",
                                    account_id=acc_id,
                                    account_name=account_name,
                                    note_id=note_id
                                )
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_RATE_LIMITED,
                                        note_id=note_id,
                                        message=str(msg),
                                        extra={'retry': retry_attempt + 1}
                                    )
                                wait_time = get_adaptive_delay_manager().get_rate_limit_wait()
                                time.sleep(wait_time)
                                continue
                            
                            if is_unavailable:
                                logger.warning(f"Note {note_id} unavailable: {msg}")
                                if sync_log:
                                    sync_log.add_issue(
                                        SyncLogCollector.TYPE_UNAVAILABLE,
                                        note_id=note_id,
                                        message=str(msg)
                                    )
                                break
                            
                            if not success:
                                if SyncService._handle_auth_error(msg):
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
                                    break
                                elif SyncService._is_xsec_token_error(msg):
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_TOKEN_REFRESH,
                                            note_id=note_id,
                                            message=f"xsec_token invalid: {msg}"
                                        )
                                    break
                                else:
                                    logger.warning(f"Failed to get note detail for {note_id}: {msg}")
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_FETCH_FAILED,
                                            note_id=note_id,
                                            message=str(msg)
                                        )
                                    break

                            if success and note_info:
                                try:
                                    note_info['xsec_token'] = note_xsec_token
                                    SyncService._save_note(note_info, download_media=True, auto_commit=False)
                                    detail_saved = True
                                    SyncService._record_success()
                                    if sync_log:
                                        sync_log.record_success()
                                    break
                                except Exception as e:
                                    logger.warning(f"Error saving note {note_id}: {e}")
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_FETCH_FAILED,
                                            note_id=note_id,
                                            message=f"Save error: {str(e)}"
                                        )
                                    break
                            else:
                                if '频次' in str(msg):
                                    rate_limited = True
                                    if sync_log:
                                        sync_log.add_issue(
                                            SyncLogCollector.TYPE_RATE_LIMITED,
                                            note_id=note_id,
                                            message=f"Empty response: {msg}"
                                        )
                                    continue
                                break
                        
                        # Extended wait on rate limit
                        if rate_limited and not detail_saved:
                            total_wait = get_adaptive_delay_manager().get_rate_limit_wait() * 1.5
                            time.sleep(total_wait)
                        
                        # Fallback to list data
                        if not detail_saved:
                            if sync_log:
                                sync_log.add_issue(
                                    SyncLogCollector.TYPE_MISSING_FIELD,
                                    note_id=note_id,
                                    message="Fallback to list data, missing: upload_time, collected_count, etc.",
                                    fields=['upload_time', 'collected_count', 'comment_count', 'share_count']
                                )
                            
                            try:
                                if note_xsec_token:
                                    simple_note['xsec_token'] = note_xsec_token
                                # Use list note converter instead of handle_note_info (which expects detail format)
                                cleaned_data = SyncService._convert_list_note(simple_note, user_id=account.user_id)
                                SyncService._save_note(cleaned_data, download_media=False, auto_commit=False)
                            except Exception as e:
                                logger.warning(f"Error saving note {note_id} with list data: {e}")
                        
                        SyncService._sleep_with_jitter(sync_mode)
                    
                    # Update progress
                    account.loaded_msgs = idx + 1
                    account.progress = int(((idx + 1) / total) * 100) if total > 0 else 100
                    
                    # Batch commit every 5 notes
                    if (idx + 1) % 5 == 0 or idx == total - 1:
                        account.sync_heartbeat = datetime.utcnow()
                        db.session.commit()
                        
                        sync_log_broadcaster.broadcast_progress(
                            account_id=acc_id,
                            status='processing',
                            progress=account.progress,
                            loaded_msgs=account.loaded_msgs,
                            total_msgs=total
                        )
                    
                # Save remaining batch
                if sync_mode == 'fast' and fast_sync_batch:
                    try:
                        inserted, updated = SyncService._bulk_save_notes(
                            fast_sync_batch, existing_note_ids_cache, existing_notes_cache
                        )
                        logger.debug(f"[FastSync] Final batch: {inserted} new, {updated} updated")
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
                    
                    if sync_log:
                        logs_data = sync_log.finalize()
                        account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                        
                        summary = logs_data.get('summary', {})
                        issues_count = sum([
                            summary.get('rate_limited', 0),
                            summary.get('missing_field', 0),
                            summary.get('fetch_failed', 0)
                        ])
                        if issues_count > 0:
                            account.error_message = (
                                f"Sync completed with {issues_count} issues: "
                                f"rate_limited={summary.get('rate_limited', 0)}, "
                                f"missing={summary.get('missing_field', 0)}, "
                                f"failed={summary.get('fetch_failed', 0)}"
                            )
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed', summary)
                    else:
                        sync_log_broadcaster.broadcast_completed(acc_id, 'completed')
                else:
                    if account.status == 'processing':
                        account.status = 'failed'
                        mode_name = 'deep sync' if sync_mode == 'deep' else 'fast sync'
                        account.error_message = account.error_message or f"User stopped {mode_name}"
                        account.sync_heartbeat = None
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
                        account.status = 'failed'
                        account.error_message = f"Sync error: {str(e)}"
                        account.sync_heartbeat = None
                        if sync_log:
                            sync_log.add_issue(
                                SyncLogCollector.TYPE_FETCH_FAILED,
                                message=f"Sync error: {str(e)}"
                            )
                            logs_data = sync_log.finalize()
                            account.sync_logs = json.dumps(logs_data, ensure_ascii=False)
                        db.session.commit()
                except Exception as inner_e:
                    logger.error(f"Error updating account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _bulk_save_notes(
        notes_data_list: List[Dict],
        existing_note_ids: Optional[Set[str]] = None,
        existing_notes_cache: Optional[Dict[str, Note]] = None
    ) -> Tuple[int, int]:
        """Bulk save notes to database.
        
        Args:
            notes_data_list: List of note data dictionaries
            existing_note_ids: Set of existing note IDs
            existing_notes_cache: Cache of existing Note objects
        
        Returns:
            Tuple of (inserted_count, updated_count)
        """
        if not notes_data_list:
            return 0, 0
        
        try:
            # Pre-fetch existing notes if not provided
            if existing_note_ids is None or existing_notes_cache is None:
                note_ids = [n.get('note_id') for n in notes_data_list if n.get('note_id')]
                existing_notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
                existing_note_ids = {n.note_id for n in existing_notes}
                existing_notes_cache = {n.note_id: n for n in existing_notes}
            
            insert_mappings = []
            update_count = 0
            now = datetime.utcnow()
            cover_tasks = []
            
            for note_data in notes_data_list:
                note_id = note_data.get('note_id')
                if not note_id:
                    continue
                
                # Calculate cover URL
                cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
                if not cover_remote:
                    imgs = note_data.get('image_list') or []
                    cover_remote = imgs[0] if imgs else None
                
                if cover_remote:
                    cover_tasks.append((cover_remote, note_id))
                
                if note_id in existing_note_ids:
                    # Update existing
                    note = existing_notes_cache.get(note_id)
                    if note:
                        note.nickname = note_data['nickname']
                        note.avatar = note_data['avatar']
                        note.title = note_data['title']
                        if note_data['desc']:
                            note.desc = note_data['desc']
                        note.type = note_data['note_type']
                        
                        if note_data['liked_count'] is not None:
                            note.liked_count = note_data['liked_count']
                        if note_data['collected_count'] is not None:
                            note.collected_count = note_data['collected_count']
                        if note_data['comment_count'] is not None:
                            note.comment_count = note_data['comment_count']
                        if note_data['share_count'] is not None:
                            note.share_count = note_data['share_count']
                        if note_data['upload_time']:
                            note.upload_time = note_data['upload_time']
                        if note_data['video_addr']:
                            note.video_addr = note_data['video_addr']
                        if note_data['image_list']:
                            new_count = len(note_data['image_list'])
                            old_list = json.loads(note.image_list) if note.image_list else []
                            if new_count > len(old_list) or len(old_list) <= 1:
                                note.image_list = json.dumps(note_data['image_list'])
                        if note_data['tags']:
                            note.tags = json.dumps(note_data['tags'])
                        if note_data['ip_location']:
                            note.ip_location = note_data['ip_location']
                        if cover_remote:
                            note.cover_remote = cover_remote
                        if note_data.get('xsec_token'):
                            note.xsec_token = note_data['xsec_token']
                        note.last_updated = now
                        update_count += 1
                else:
                    # Insert new
                    mapping = {
                        'note_id': note_id,
                        'user_id': note_data['user_id'],
                        'nickname': note_data['nickname'],
                        'avatar': note_data['avatar'],
                        'title': note_data['title'],
                        'desc': note_data['desc'] or '',
                        'type': note_data['note_type'],
                        'liked_count': note_data['liked_count'] or 0,
                        'collected_count': note_data['collected_count'] or 0,
                        'comment_count': note_data['comment_count'] or 0,
                        'share_count': note_data['share_count'] or 0,
                        'upload_time': note_data['upload_time'] or '',
                        'video_addr': note_data['video_addr'] or '',
                        'image_list': json.dumps(note_data['image_list']) if note_data['image_list'] else '[]',
                        'tags': json.dumps(note_data['tags']) if note_data['tags'] else '[]',
                        'ip_location': note_data['ip_location'] or '',
                        'cover_remote': cover_remote or '',
                        'cover_local': '',
                        'xsec_token': note_data.get('xsec_token') or '',
                        'last_updated': now,
                    }
                    insert_mappings.append(mapping)
            
            if insert_mappings:
                db.session.bulk_insert_mappings(Note, insert_mappings)
            
            db.session.commit()
            
            # Submit cover downloads to async queue
            if cover_tasks:
                queue = get_media_download_queue()
                for cover_url, nid in cover_tasks:
                    queue.submit_cover_download(cover_url, nid, callback=SyncService._update_cover_local)
            
            return len(insert_mappings), update_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"[BulkSave] Failed: {e}")
            raise
    
    @staticmethod
    def _save_note(note_data: Dict, download_media: bool = False, auto_commit: bool = True) -> None:
        """Save a single note to database.
        
        Args:
            note_data: Note data dictionary
            download_media: Whether to download media files
            auto_commit: Whether to auto-commit transaction
        """
        try:
            note_id = note_data.get('note_id')
            if not note_id:
                logger.debug(f"Skipping note save: note_id is empty")
                return

            # Calculate cover
            cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
            if not cover_remote:
                imgs = note_data.get('image_list') or []
                cover_remote = imgs[0] if imgs else None
            
            note = Note.query.filter_by(note_id=note_id).first()
            
            if note:
                # Update existing
                note.nickname = note_data['nickname']
                note.avatar = note_data['avatar']
                note.title = note_data['title']
                if note_data['desc']:
                    note.desc = note_data['desc']
                note.type = note_data['note_type']
                
                if note_data['liked_count'] is not None:
                    note.liked_count = note_data['liked_count']
                if note_data['collected_count'] is not None:
                    note.collected_count = note_data['collected_count']
                if note_data['comment_count'] is not None:
                    note.comment_count = note_data['comment_count']
                if note_data['share_count'] is not None:
                    note.share_count = note_data['share_count']
                if note_data['upload_time']:
                    note.upload_time = note_data['upload_time']
                if note_data['video_addr']:
                    note.video_addr = note_data['video_addr']
                if note_data['image_list']:
                    new_count = len(note_data['image_list'])
                    old_list = json.loads(note.image_list) if note.image_list else []
                    if new_count > len(old_list) or len(old_list) <= 1:
                        note.image_list = json.dumps(note_data['image_list'])
                if note_data['tags']:
                    note.tags = json.dumps(note_data['tags'])
                if note_data['ip_location']:
                    note.ip_location = note_data['ip_location']
                if cover_remote:
                    note.cover_remote = cover_remote
                if note_data.get('xsec_token'):
                    note.xsec_token = note_data['xsec_token']
                note.last_updated = datetime.utcnow()
            else:
                # Create new
                note = Note(
                    note_id=note_id,
                    user_id=note_data['user_id'],
                    nickname=note_data['nickname'],
                    avatar=note_data['avatar'],
                    title=note_data['title'],
                    desc=note_data['desc'] or '',
                    type=note_data['note_type'],
                    liked_count=note_data['liked_count'] or 0,
                    collected_count=note_data['collected_count'] or 0,
                    comment_count=note_data['comment_count'] or 0,
                    share_count=note_data['share_count'] or 0,
                    upload_time=note_data['upload_time'] or '',
                    video_addr=note_data['video_addr'] or '',
                    image_list=json.dumps(note_data['image_list']) if note_data['image_list'] else '[]',
                    tags=json.dumps(note_data['tags']) if note_data['tags'] else '[]',
                    ip_location=note_data['ip_location'] or '',
                    cover_remote=cover_remote or '',
                    cover_local='',
                    xsec_token=note_data.get('xsec_token') or '',
                )
                db.session.add(note)
            
            if auto_commit:
                db.session.commit()
            
            # Async media download
            queue = get_media_download_queue()
            if cover_remote:
                queue.submit_cover_download(cover_remote, note_id, callback=SyncService._update_cover_local)
            if download_media:
                queue.submit_media_download(note_id, note_data)
                
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Error saving note {note_data.get('note_id')}: {e}")
            raise
    
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
