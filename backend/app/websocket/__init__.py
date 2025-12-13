"""
WebSocket 模块 - 使用 Flask-SocketIO 实现实时推送
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
from ..utils.logger import get_logger

logger = get_logger('websocket')

# Global SocketIO instance
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')


def init_socketio(app):
    """Initialize SocketIO with Flask app"""
    socketio.init_app(app)
    logger.info("[WebSocket] SocketIO initialized")
    return socketio


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("[WebSocket] Client connected")
    emit('connected', {'status': 'ok', 'message': 'WebSocket connected'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("[WebSocket] Client disconnected")


@socketio.on('subscribe_sync')
def handle_subscribe_sync(data):
    """Subscribe to sync progress updates for specific accounts
    
    Args:
        data: {'account_ids': [1, 2, 3]} or {'all': True}
    """
    if data.get('all'):
        join_room('sync_all')
        logger.info("[WebSocket] Client subscribed to all sync updates")
        emit('subscribed', {'room': 'sync_all'})
    else:
        account_ids = data.get('account_ids', [])
        for acc_id in account_ids:
            room = f'sync_{acc_id}'
            join_room(room)
        logger.info(f"[WebSocket] Client subscribed to accounts: {account_ids}")
        emit('subscribed', {'accounts': account_ids})


@socketio.on('unsubscribe_sync')
def handle_unsubscribe_sync(data):
    """Unsubscribe from sync updates"""
    if data.get('all'):
        leave_room('sync_all')
        logger.info("[WebSocket] Client unsubscribed from all sync updates")
    else:
        account_ids = data.get('account_ids', [])
        for acc_id in account_ids:
            leave_room(f'sync_{acc_id}')
        logger.info(f"[WebSocket] Client unsubscribed from accounts: {account_ids}")


def broadcast_sync_progress(account_id: int, data: dict):
    """Broadcast sync progress to subscribed clients
    
    Args:
        account_id: Account ID
        data: Progress data including status, progress, loaded_msgs, total_msgs, etc.
    """
    # Broadcast to specific account room
    socketio.emit('sync_progress', {
        'account_id': account_id,
        **data
    }, room=f'sync_{account_id}')
    
    # Also broadcast to all-sync room
    socketio.emit('sync_progress', {
        'account_id': account_id,
        **data
    }, room='sync_all')


def broadcast_sync_log(log_entry: dict):
    """Broadcast sync log entry to all subscribed clients
    
    Args:
        log_entry: Log entry dict with level, message, account_id, etc.
    """
    account_id = log_entry.get('account_id')
    
    # Broadcast to specific account room if account_id is present
    if account_id:
        socketio.emit('sync_log', log_entry, room=f'sync_{account_id}')
    
    # Always broadcast to all-sync room
    socketio.emit('sync_log', log_entry, room='sync_all')


def broadcast_sync_completed(account_id: int, status: str, summary: dict = None):
    """Broadcast sync completion event
    
    Args:
        account_id: Account ID
        status: Final status ('completed', 'failed', 'cancelled')
        summary: Optional summary dict
    """
    data = {
        'account_id': account_id,
        'status': status,
        'summary': summary or {}
    }
    
    socketio.emit('sync_completed', data, room=f'sync_{account_id}')
    socketio.emit('sync_completed', data, room='sync_all')
