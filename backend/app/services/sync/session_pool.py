"""
Request Session Pool - HTTP connection pooling for performance

This module provides HTTP session pooling to reuse TCP connections,
reducing latency from repeated handshakes and SSL negotiations.
"""
import threading
from typing import Dict

import requests
from requests.adapters import HTTPAdapter

from ...utils.logger import get_logger

logger = get_logger('session_pool')


class RequestSessionPool:
    """HTTP request session pool for connection reuse.
    
    Uses requests.Session with connection pooling for better performance:
    1. Avoids repeated TCP handshakes
    2. Reuses SSL/TLS sessions
    3. Supports HTTP Keep-Alive
    4. Connection pool management prevents leaks
    
    This class implements the singleton pattern to ensure a single
    connection pool is shared across the application.
    
    Example:
        >>> pool = get_request_session_pool()
        >>> response = pool.get('https://api.example.com/data', timeout=10)
        >>> stats = pool.get_stats()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Connection pool configuration
    POOL_CONNECTIONS = 10  # Number of connection pools to cache
    POOL_MAXSIZE = 10      # Max connections per host
    MAX_RETRIES = 3        # Automatic retries on connection errors
    
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
        
        # Create session with connection pooling
        self._session = requests.Session()
        
        # Configure connection pool adapter
        adapter = HTTPAdapter(
            pool_connections=self.POOL_CONNECTIONS,
            pool_maxsize=self.POOL_MAXSIZE,
            max_retries=self.MAX_RETRIES,
            pool_block=False
        )
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
        
        # Statistics
        self._stats = {'requests': 0, 'errors': 0}
        self._stats_lock = threading.Lock()
        
        self._initialized = True
        logger.info(
            f"[RequestSessionPool] Initialized: "
            f"pool_connections={self.POOL_CONNECTIONS}, pool_maxsize={self.POOL_MAXSIZE}"
        )
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Send GET request using pooled session.
        
        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.get()
            
        Returns:
            requests.Response object
            
        Raises:
            requests.RequestException: On request failure
        """
        with self._stats_lock:
            self._stats['requests'] += 1
        
        try:
            return self._session.get(url, **kwargs)
        except Exception as e:
            with self._stats_lock:
                self._stats['errors'] += 1
            raise
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Send POST request using pooled session.
        
        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.post()
            
        Returns:
            requests.Response object
            
        Raises:
            requests.RequestException: On request failure
        """
        with self._stats_lock:
            self._stats['requests'] += 1
        
        try:
            return self._session.post(url, **kwargs)
        except Exception as e:
            with self._stats_lock:
                self._stats['errors'] += 1
            raise
    
    @property
    def session(self) -> requests.Session:
        """Get the underlying session for direct use.
        
        Returns:
            The requests.Session instance
        """
        return self._session
    
    def get_stats(self) -> Dict:
        """Get request statistics.
        
        Returns:
            Dictionary with request and error counts
        """
        with self._stats_lock:
            return self._stats.copy()
    
    def close(self) -> None:
        """Close all connections in the pool."""
        self._session.close()
        logger.info("[RequestSessionPool] Session pool closed")


# Global singleton instance
_request_session_pool: RequestSessionPool = None


def get_request_session_pool() -> RequestSessionPool:
    """Get global request session pool instance (singleton pattern).
    
    Returns:
        The global RequestSessionPool instance
    """
    global _request_session_pool
    if _request_session_pool is None:
        _request_session_pool = RequestSessionPool()
    return _request_session_pool
