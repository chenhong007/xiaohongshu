"""
同步日志广播服务 - 用于实时推送同步日志到前端
支持 SSE（Server-Sent Events）和 WebSocket 双通道推送
"""
import json
import queue
import threading
from datetime import datetime
from typing import Dict, Generator

# 日志级别
LOG_LEVEL_DEBUG = 'debug'
LOG_LEVEL_INFO = 'info'
LOG_LEVEL_WARN = 'warn'
LOG_LEVEL_ERROR = 'error'


class SyncLogBroadcaster:
    """同步日志广播器 - 单例模式
    
    支持双通道推送：
    1. SSE (Server-Sent Events) - 向后兼容
    2. WebSocket - 新增实时推送
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # SSE 订阅者队列字典 {client_id: queue}
        self._subscribers: Dict[str, queue.Queue] = {}
        self._sub_lock = threading.Lock()
        self._client_counter = 0
        
        # WebSocket enabled flag
        self._websocket_enabled = False
    
    def enable_websocket(self):
        """Enable WebSocket broadcasting"""
        self._websocket_enabled = True
    
    def subscribe(self) -> tuple:
        """订阅日志流，返回 (client_id, generator)"""
        with self._sub_lock:
            self._client_counter += 1
            client_id = f"client_{self._client_counter}"
            q = queue.Queue(maxsize=100)  # 限制队列大小防止内存溢出
            self._subscribers[client_id] = q
        
        return client_id, self._create_generator(client_id, q)
    
    def unsubscribe(self, client_id: str):
        """取消订阅"""
        with self._sub_lock:
            if client_id in self._subscribers:
                del self._subscribers[client_id]
    
    def _create_generator(self, client_id: str, q: queue.Queue) -> Generator:
        """创建 SSE 事件生成器"""
        try:
            while True:
                try:
                    # 超时等待，便于检测连接断开
                    message = q.get(timeout=30)
                    if message is None:  # 关闭信号
                        break
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    # 发送心跳保持连接
                    yield f": heartbeat\n\n"
        finally:
            self.unsubscribe(client_id)
    
    def _broadcast_via_websocket(self, log_entry: dict):
        """Broadcast log entry via WebSocket"""
        if not self._websocket_enabled:
            return
        
        try:
            from ..websocket import broadcast_sync_log
            broadcast_sync_log(log_entry)
        except ImportError:
            pass  # WebSocket module not available
        except Exception as e:
            pass  # Silently fail to avoid breaking sync
    
    def broadcast(self, level: str, message: str, account_id: int = None, 
                  account_name: str = None, note_id: str = None, extra: dict = None):
        """广播日志消息到所有订阅者（SSE + WebSocket）"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': level,
            'message': message,
        }
        
        if account_id is not None:
            log_entry['account_id'] = account_id
        if account_name:
            log_entry['account_name'] = account_name
        if note_id:
            log_entry['note_id'] = note_id
        if extra:
            log_entry['extra'] = extra
        
        # Broadcast via SSE (existing mechanism)
        with self._sub_lock:
            dead_clients = []
            for client_id, q in self._subscribers.items():
                try:
                    q.put_nowait(log_entry)
                except queue.Full:
                    # 队列满了，移除旧消息
                    try:
                        q.get_nowait()
                        q.put_nowait(log_entry)
                    except:
                        dead_clients.append(client_id)
            
            # 清理死客户端
            for client_id in dead_clients:
                del self._subscribers[client_id]
        
        # Broadcast via WebSocket (new mechanism)
        self._broadcast_via_websocket(log_entry)
    
    def broadcast_progress(self, account_id: int, status: str, progress: int,
                           loaded_msgs: int, total_msgs: int, **kwargs):
        """Broadcast sync progress update via WebSocket
        
        This is a specialized method for progress updates that goes directly
        to WebSocket without SSE overhead.
        """
        if not self._websocket_enabled:
            return
        
        try:
            from ..websocket import broadcast_sync_progress
            broadcast_sync_progress(account_id, {
                'status': status,
                'progress': progress,
                'loaded_msgs': loaded_msgs,
                'total_msgs': total_msgs,
                **kwargs
            })
        except ImportError:
            pass
        except Exception:
            pass
    
    def broadcast_completed(self, account_id: int, status: str, summary: dict = None):
        """Broadcast sync completion event via WebSocket"""
        if not self._websocket_enabled:
            return
        
        try:
            from ..websocket import broadcast_sync_completed
            broadcast_sync_completed(account_id, status, summary)
        except ImportError:
            pass
        except Exception:
            pass
    
    def info(self, message: str, **kwargs):
        """广播 INFO 级别日志"""
        self.broadcast(LOG_LEVEL_INFO, message, **kwargs)
    
    def warn(self, message: str, **kwargs):
        """广播 WARN 级别日志"""
        self.broadcast(LOG_LEVEL_WARN, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """广播 ERROR 级别日志"""
        self.broadcast(LOG_LEVEL_ERROR, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """广播 DEBUG 级别日志"""
        self.broadcast(LOG_LEVEL_DEBUG, message, **kwargs)
    
    def broadcast_cookie_status(self, status: str, message: str, extra: dict = None):
        """Broadcast Cookie status change event
        
        Args:
            status: Cookie status type
                - 'invalid': Cookie expired or invalid
                - 'rate_limited': Access frequency limited
                - 'valid': Cookie is valid (after re-validation)
            message: Human readable message
            extra: Additional data (rate_limit_count, cooldown_seconds, etc.)
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': LOG_LEVEL_ERROR if status == 'invalid' else LOG_LEVEL_WARN,
            'type': 'cookie_status',
            'status': status,
            'message': message,
        }
        
        if extra:
            log_entry['extra'] = extra
        
        # Broadcast via SSE
        with self._sub_lock:
            dead_clients = []
            for client_id, q in self._subscribers.items():
                try:
                    q.put_nowait(log_entry)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(log_entry)
                    except:
                        dead_clients.append(client_id)
            
            for client_id in dead_clients:
                del self._subscribers[client_id]
        
        # Broadcast via WebSocket
        self._broadcast_via_websocket(log_entry)
    
    @property
    def subscriber_count(self) -> int:
        """当前订阅者数量"""
        with self._sub_lock:
            return len(self._subscribers)


# 全局单例
sync_log_broadcaster = SyncLogBroadcaster()
