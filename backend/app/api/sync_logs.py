"""
同步日志 SSE 推送 API
"""
from flask import Blueprint, Response, stream_with_context

from ..services.sync_log_broadcaster import sync_log_broadcaster

sync_logs_bp = Blueprint('sync_logs', __name__)


@sync_logs_bp.route('/sync-logs/stream', methods=['GET'])
def stream_sync_logs():
    """
    SSE 端点 - 实时推送同步日志
    
    前端使用 EventSource 连接此端点，实时接收同步过程中的日志。
    
    返回格式 (SSE):
        data: {"timestamp": "...", "level": "info|warn|error", "message": "...", ...}
    """
    client_id, generator = sync_log_broadcaster.subscribe()
    
    def generate():
        # 发送连接成功消息
        yield f"data: {{\"level\": \"info\", \"message\": \"已连接同步日志流\", \"client_id\": \"{client_id}\"}}\n\n"
        yield from generator
    
    response = Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # 禁用 nginx 缓冲
        }
    )
    return response


@sync_logs_bp.route('/sync-logs/status', methods=['GET'])
def get_status():
    """获取日志广播状态"""
    from ..utils.responses import success_response
    return success_response({
        'subscriber_count': sync_log_broadcaster.subscriber_count
    })
