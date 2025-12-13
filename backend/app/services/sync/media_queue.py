"""
Media Download Queue - Async media downloading with thread pool

This module provides asynchronous media downloading to prevent
blocking the main sync flow while downloading covers and images.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from ...utils.logger import get_logger
from ...config import Config

logger = get_logger('media_queue')


class MediaDownloadQueue:
    """Async media download queue using thread pool.
    
    Singleton pattern ensures a single shared download queue.
    Supports two task types:
    1. cover - Cover image download
    2. media - Full media file download (images, videos)
    
    Example:
        >>> queue = get_media_download_queue()
        >>> queue.submit_cover_download(url, note_id, callback=update_db)
        >>> queue.submit_media_download(note_id, note_data)
        >>> queue.wait_completion(timeout=60)
        >>> stats = queue.get_stats()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Thread pool configuration
    MAX_WORKERS = 4  # Concurrent download threads
    QUEUE_TIMEOUT = 10  # Seconds to wait for task submission
    
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
        
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_WORKERS,
            thread_name_prefix='media_dl'
        )
        self._futures: List = []
        self._futures_lock = threading.Lock()
        self._stats = {'submitted': 0, 'completed': 0, 'failed': 0}
        self._stats_lock = threading.Lock()
        self._initialized = True
        logger.info(f"[MediaDownloadQueue] Initialized with {self.MAX_WORKERS} workers")
    
    def submit_cover_download(
        self,
        remote_url: str,
        note_id: str,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Submit a cover download task to the queue.
        
        Args:
            remote_url: Remote URL of the cover image
            note_id: Note ID for filename generation
            callback: Optional callback(note_id, local_path) called after download
        """
        if not remote_url or not note_id:
            return
        
        def _download_task():
            try:
                local_path = self._do_download_cover(remote_url, note_id)
                if callback and local_path:
                    callback(note_id, local_path)
                with self._stats_lock:
                    self._stats['completed'] += 1
                return local_path
            except Exception as e:
                logger.warning(f"[MediaDownloadQueue] Cover download failed for {note_id}: {e}")
                with self._stats_lock:
                    self._stats['failed'] += 1
                return None
        
        try:
            future = self._executor.submit(_download_task)
            with self._futures_lock:
                self._futures.append(future)
                with self._stats_lock:
                    self._stats['submitted'] += 1
        except Exception as e:
            logger.warning(f"[MediaDownloadQueue] Failed to submit cover task for {note_id}: {e}")
    
    def submit_media_download(self, note_id: str, note_data: Dict) -> None:
        """Submit a full media download task to the queue.
        
        Args:
            note_id: Note ID
            note_data: Note data dict containing image_list and video_addr
        """
        if not note_id or not note_data:
            return
        
        def _download_task():
            try:
                self._do_download_all_media(note_id, note_data)
                with self._stats_lock:
                    self._stats['completed'] += 1
            except Exception as e:
                logger.warning(f"[MediaDownloadQueue] Media download failed for {note_id}: {e}")
                with self._stats_lock:
                    self._stats['failed'] += 1
        
        try:
            future = self._executor.submit(_download_task)
            with self._futures_lock:
                self._futures.append(future)
                with self._stats_lock:
                    self._stats['submitted'] += 1
        except Exception as e:
            logger.warning(f"[MediaDownloadQueue] Failed to submit media task for {note_id}: {e}")
    
    def wait_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all pending download tasks to complete.
        
        Args:
            timeout: Maximum seconds to wait. None means wait forever.
        
        Returns:
            True if all tasks completed, False if timeout
        """
        with self._futures_lock:
            futures_copy = self._futures[:]
        
        if not futures_copy:
            return True
        
        try:
            completed = 0
            for future in as_completed(futures_copy, timeout=timeout):
                completed += 1
            
            # Clean up completed futures
            with self._futures_lock:
                self._futures = [f for f in self._futures if not f.done()]
            
            logger.info(f"[MediaDownloadQueue] Wait completed: {completed} tasks finished")
            return True
        except TimeoutError:
            logger.warning(f"[MediaDownloadQueue] Wait timeout after {timeout}s")
            return False
    
    def get_stats(self) -> Dict:
        """Get current queue statistics.
        
        Returns:
            Dictionary with submitted, completed, failed, and pending counts
        """
        with self._stats_lock:
            pending = 0
            with self._futures_lock:
                pending = len([f for f in self._futures if not f.done()])
            return {
                'submitted': self._stats['submitted'],
                'completed': self._stats['completed'],
                'failed': self._stats['failed'],
                'pending': pending
            }
    
    def _do_download_cover(self, remote_url: str, note_id: str) -> Optional[str]:
        """Actual cover download implementation (runs in worker thread).
        
        Args:
            remote_url: Remote URL to download
            note_id: Note ID for filename
            
        Returns:
            Local API path if successful, None otherwise
        """
        if not remote_url:
            return None
        
        try:
            # Lazy import to avoid circular imports
            from .session_pool import get_request_session_pool
            
            # Import Spider_XHS headers utility
            try:
                from Spider_XHS.xhs_utils.xhs_util import get_common_headers
                headers = get_common_headers()
            except ImportError:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            
            Config.init_paths()
            parsed = urlparse(remote_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filename = f"{note_id}_cover{ext}"
            filepath = os.path.join(Config.MEDIA_PATH, filename)
            
            # Skip if file exists and is valid
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                return f"/api/media/{filename}"
            
            session_pool = get_request_session_pool()
            
            # Retry mechanism with shorter timeout for async downloads
            for attempt in range(2):
                try:
                    resp = session_pool.get(remote_url, headers=headers, stream=True, timeout=10)
                    if resp.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        logger.debug(f"[MediaDownloadQueue] Downloaded cover for {note_id}")
                        return f"/api/media/{filename}"
                    elif resp.status_code == 403:
                        logger.warning(f"[MediaDownloadQueue] Cover 403 for {note_id}, attempt {attempt+1}")
                        time.sleep(0.5)
                except Exception as dl_err:
                    logger.warning(f"[MediaDownloadQueue] Cover attempt {attempt+1} failed: {dl_err}")
                    time.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"[MediaDownloadQueue] Cover error for {note_id}: {e}")
        return None
    
    def _do_download_all_media(self, note_id: str, note_data: Dict) -> None:
        """Actual media download implementation (runs in worker thread).
        
        Args:
            note_id: Note ID
            note_data: Note data dictionary
        """
        try:
            # Lazy import to avoid circular imports
            from .session_pool import get_request_session_pool
            
            # Import Spider_XHS headers utility
            try:
                from Spider_XHS.xhs_utils.xhs_util import get_common_headers
                headers = get_common_headers()
            except ImportError:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            
            Config.init_paths()
            note_dir = os.path.join(Config.MEDIA_PATH, str(note_id))
            if not os.path.exists(note_dir):
                os.makedirs(note_dir)
            
            session_pool = get_request_session_pool()
            downloaded_count = 0
            
            # Download images
            if note_data.get('image_list'):
                for idx, img_url in enumerate(note_data['image_list']):
                    ext = '.jpg'
                    filename = f"image_{idx}{ext}"
                    filepath = os.path.join(note_dir, filename)
                    
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                        continue
                    
                    # Build fallback URLs
                    urls_to_try = [img_url]
                    if 'sns-img-qc.xhscdn.com' in img_url or 'sns-img-hw.xhscdn.com' in img_url:
                        img_id = img_url.split('/')[-1].split('?')[0]
                        urls_to_try.extend([
                            f'https://ci.xiaohongshu.com/{img_id}?imageView2/2/w/format/jpg',
                            f'https://sns-img-hw.xhscdn.com/{img_id}?imageView2/2/w/format/jpg',
                        ])
                    elif 'ci.xiaohongshu.com' in img_url and '?' not in img_url:
                        urls_to_try.append(f'{img_url}?imageView2/2/w/format/jpg')
                    
                    for try_url in urls_to_try:
                        try:
                            resp = session_pool.get(try_url, headers=headers, stream=True, timeout=15)
                            if resp.status_code == 200 and int(resp.headers.get('content-length', 0)) > 1024:
                                with open(filepath, 'wb') as f:
                                    for chunk in resp.iter_content(8192):
                                        f.write(chunk)
                                downloaded_count += 1
                                break
                        except Exception:
                            continue
            
            if downloaded_count > 0:
                logger.info(f"[MediaDownloadQueue] Archived {downloaded_count} files for note {note_id}")
                
        except Exception as e:
            logger.error(f"[MediaDownloadQueue] Media error for {note_id}: {e}")
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool.
        
        Args:
            wait: If True, wait for pending tasks to complete
        """
        self._executor.shutdown(wait=wait)
        logger.info("[MediaDownloadQueue] Thread pool shutdown")


# Global singleton instance
_media_download_queue: MediaDownloadQueue = None


def get_media_download_queue() -> MediaDownloadQueue:
    """Get the global media download queue instance (singleton pattern).
    
    Returns:
        The global MediaDownloadQueue instance
    """
    global _media_download_queue
    if _media_download_queue is None:
        _media_download_queue = MediaDownloadQueue()
    return _media_download_queue
