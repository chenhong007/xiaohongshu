"""
API 蓝图
"""
from .accounts import accounts_bp
from .notes import notes_bp
from .auth import auth_bp
from .search import search_bp
from .sync_logs import sync_logs_bp

__all__ = ['accounts_bp', 'notes_bp', 'auth_bp', 'search_bp', 'sync_logs_bp']

