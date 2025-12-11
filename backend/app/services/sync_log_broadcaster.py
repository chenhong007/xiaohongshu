"""
同步日志广播服务 - 用于实时推送同步日志到前端
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
    """同步日志广播器 - 单例模式"""
    
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
        
        # 订阅者队列字典 {client_id: queue}
        self._subscribers: Dict[str, queue.Queue] = {}
        self._sub_lock = threading.Lock()
        self._client_counter = 0
    
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
    
    def broadcast(self, level: str, message: str, account_id: int = None, 
                  account_name: str = None, note_id: str = None, extra: dict = None):
        """广播日志消息到所有订阅者"""
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
    
    @property
    def subscriber_count(self) -> int:
        """当前订阅者数量"""
        with self._sub_lock:
            return len(self._subscribers)


# 全局单例
sync_log_broadcaster = SyncLogBroadcaster()
