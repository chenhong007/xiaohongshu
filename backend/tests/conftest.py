"""
Pytest Configuration and Fixtures

This module provides shared fixtures for all tests.
"""
import os
import sys
import pytest

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.config import TestingConfig


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app(TestingConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing."""
    with app.app_context():
        db.session.begin_nested()
        yield db.session
        db.session.rollback()


@pytest.fixture
def sample_account_data():
    """Sample account data for testing."""
    return {
        'user_id': 'test_user_123',
        'name': 'Test User',
        'avatar': 'https://example.com/avatar.jpg',
        'red_id': 'testuser',
        'fans': 1000,
    }


@pytest.fixture
def sample_note_data():
    """Sample note data for testing."""
    return {
        'note_id': 'test_note_123',
        'user_id': 'test_user_123',
        'nickname': 'Test User',
        'avatar': 'https://example.com/avatar.jpg',
        'title': 'Test Note Title',
        'desc': 'Test note description',
        'note_type': 'normal',
        'liked_count': 100,
        'collected_count': 50,
        'comment_count': 25,
        'share_count': 10,
        'upload_time': '2024-01-01 12:00:00',
        'video_addr': None,
        'image_list': ['https://example.com/img1.jpg'],
        'tags': ['tag1', 'tag2'],
        'ip_location': 'Beijing',
    }
