"""
Authentication Error Handler - Centralized auth error handling

Provides unified handling for authentication and authorization errors.
"""
from typing import Optional, Tuple, Set, Callable
from datetime import datetime

from ...models import Cookie, Account
from ...extensions import db
from ...utils.logger import get_logger
from ..sync_log_broadcaster import sync_log_broadcaster

logger = get_logger('sync')


class AuthErrorHandler:
    """Centralized authentication error handler.
    
    Handles:
    - Cookie validity checking and invalidation
    - Auth error detection and reporting
    - Batch account failure marking
    """
    
    # Auth error keywords
    AUTH_ERROR_KEYWORDS = [
        '未登录', '登录已过期', '需要登录', '401', '403', 
        'Unauthorized', '凭据不合法', '凭据无效', '10062'
    ]
    
    @staticmethod
    def is_auth_error(msg: str) -> bool:
        """Check if error message indicates authentication issue.
        
        Args:
            msg: Error message to check
            
        Returns:
            True if message contains auth error keywords
        """
        return any(keyword in str(msg) for keyword in AuthErrorHandler.AUTH_ERROR_KEYWORDS)
    
    @staticmethod
    def handle_auth_error(
        msg: str,
        account_id: Optional[int] = None,
        account_name: Optional[str] = None,
        stop_callback: Optional[Callable[[], None]] = None,
        mark_failed_callback: Optional[Callable[[Set[int], str], None]] = None,
        remaining_account_ids: Optional[Set[int]] = None
    ) -> Tuple[bool, str]:
        """Handle authentication error.
        
        Marks Cookie as invalid, broadcasts error to frontend, and optionally
        stops sync and marks remaining accounts as failed.
        
        Args:
            msg: Error message
            account_id: Current account ID (for logging)
            account_name: Current account name (for logging)
            stop_callback: Optional callback to stop sync
            mark_failed_callback: Optional callback to mark accounts as failed
            remaining_account_ids: Set of remaining account IDs to mark as failed
            
        Returns:
            Tuple of (is_auth_error, error_message)
        """
        if not AuthErrorHandler.is_auth_error(msg):
            return False, ""
        
        logger.warning(
            f"[AuthError] Detected for account {account_name or account_id or 'unknown'}: {msg}"
        )
        
        # Mark Cookie as invalid
        try:
            cookie = Cookie.query.filter_by(is_active=True).first()
            if cookie:
                cookie.stop_run_timer()
                cookie.is_valid = False
                cookie.last_checked = datetime.utcnow()
                db.session.commit()
                logger.info("[AuthError] Cookie marked as invalid")
                
                # Broadcast cookie invalid status
                sync_log_broadcaster.broadcast_cookie_status(
                    status='invalid',
                    message=f'Cookie 已失效: {msg}',
                    extra={
                        'user_id': cookie.user_id,
                        'nickname': cookie.nickname,
                        'run_info': cookie.get_run_info(),
                    }
                )
        except Exception as e:
            logger.error(f"[AuthError] Failed to mark Cookie as invalid: {e}")
            db.session.rollback()
        
        # Build error message
        error_msg = f"Cookie expired, please re-login. Error: {msg}"
        
        # Stop sync if callback provided
        if stop_callback:
            stop_callback()
        
        # Mark remaining accounts as failed
        if mark_failed_callback and remaining_account_ids:
            mark_failed_callback(remaining_account_ids, error_msg)
        
        return True, error_msg
    
    @staticmethod
    def handle_account_auth_error(
        account: Account,
        msg: str,
        stop_callback: Optional[Callable[[], None]] = None,
        mark_failed_callback: Optional[Callable[[Set[int], str], None]] = None,
        remaining_account_ids: Optional[Set[int]] = None
    ) -> Tuple[bool, str]:
        """Handle authentication error for specific account.
        
        Convenience wrapper that extracts account info and calls handle_auth_error.
        Also updates account status to 'failed'.
        
        Args:
            account: Account object
            msg: Error message
            stop_callback: Optional callback to stop sync
            mark_failed_callback: Optional callback to mark accounts as failed
            remaining_account_ids: Set of remaining account IDs to mark as failed
            
        Returns:
            Tuple of (is_auth_error, error_message)
        """
        is_auth, error_msg = AuthErrorHandler.handle_auth_error(
            msg=msg,
            account_id=account.id,
            account_name=account.name or account.user_id,
            stop_callback=stop_callback,
            mark_failed_callback=mark_failed_callback,
            remaining_account_ids=remaining_account_ids
        )
        
        if is_auth:
            # Update account status
            account.status = 'failed'
            account.error_message = error_msg
            account.sync_heartbeat = None
            try:
                db.session.commit()
            except Exception as e:
                logger.error(f"[AuthError] Failed to update account status: {e}")
                db.session.rollback()
        
        return is_auth, error_msg


class TokenRetryHelper:
    """Helper for token refresh and API retry logic.
    
    Provides reusable pattern for:
    1. Try API call
    2. If token error, refresh token
    3. Retry API call with new token
    """
    
    @staticmethod
    def retry_with_token_refresh(
        api_call: Callable[[], Tuple[bool, str, any]],
        token_manager,
        user_id: str,
        should_refresh: Callable[[bool, str], bool],
        on_token_refreshed: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str, any]:
        """Execute API call with automatic token refresh and retry.
        
        Args:
            api_call: Function that returns (success, msg, result)
            token_manager: XsecTokenManager instance
            user_id: User ID for token refresh
            should_refresh: Function that takes (success, msg) and returns whether to refresh token
            on_token_refreshed: Optional callback when token is refreshed, receives new token
            
        Returns:
            Tuple of (success, message, result) from API call
        """
        # First attempt
        success, msg, result = api_call()
        
        # Check if should refresh token
        if should_refresh(success, msg):
            logger.debug(f"[TokenRetry] Refreshing token for user {user_id}")
            new_token = token_manager.refresh_user_token(user_id)
            
            if new_token:
                # Notify caller about new token
                if on_token_refreshed:
                    on_token_refreshed(new_token)
                
                # Retry API call
                logger.debug(f"[TokenRetry] Retrying API call with new token")
                success, msg, result = api_call()
        
        return success, msg, result

