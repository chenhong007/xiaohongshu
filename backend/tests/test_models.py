"""
Model Tests

Tests for database models: Account, Note, Cookie
"""
import pytest
from datetime import datetime

from app.models import Account, Note
from app.extensions import db


class TestAccountModel:
    """Tests for Account model."""
    
    def test_create_account(self, app, sample_account_data):
        """Test creating an account."""
        with app.app_context():
            account = Account(
                user_id=sample_account_data['user_id'],
                name=sample_account_data['name'],
                avatar=sample_account_data['avatar'],
                fans=sample_account_data['fans'],
            )
            db.session.add(account)
            db.session.commit()
            
            assert account.id is not None
            assert account.user_id == sample_account_data['user_id']
            assert account.status == 'pending'
    
    def test_account_to_dict(self, app, sample_account_data):
        """Test account serialization."""
        with app.app_context():
            account = Account(
                user_id=sample_account_data['user_id'],
                name=sample_account_data['name'],
            )
            db.session.add(account)
            db.session.commit()
            
            data = account.to_dict()
            
            assert 'id' in data
            assert data['user_id'] == sample_account_data['user_id']
            assert data['status'] == 'pending'
    
    def test_account_unique_user_id(self, app, sample_account_data):
        """Test that user_id must be unique."""
        with app.app_context():
            account1 = Account(user_id=sample_account_data['user_id'])
            db.session.add(account1)
            db.session.commit()
            
            account2 = Account(user_id=sample_account_data['user_id'])
            db.session.add(account2)
            
            with pytest.raises(Exception):
                db.session.commit()
            
            db.session.rollback()


class TestNoteModel:
    """Tests for Note model."""
    
    def test_create_note(self, app, sample_note_data):
        """Test creating a note."""
        with app.app_context():
            note = Note(
                note_id=sample_note_data['note_id'],
                user_id=sample_note_data['user_id'],
                title=sample_note_data['title'],
                desc=sample_note_data['desc'],
                type=sample_note_data['note_type'],
            )
            db.session.add(note)
            db.session.commit()
            
            assert note.note_id == sample_note_data['note_id']
    
    def test_note_to_dict(self, app, sample_note_data):
        """Test note serialization."""
        with app.app_context():
            note = Note(
                note_id=sample_note_data['note_id'],
                user_id=sample_note_data['user_id'],
                title=sample_note_data['title'],
            )
            db.session.add(note)
            db.session.commit()
            
            data = note.to_dict()
            
            assert data['note_id'] == sample_note_data['note_id']
            assert 'image_list' in data
            assert 'tags' in data
    
    def test_note_get_image_list(self, app, sample_note_data):
        """Test getting image list from JSON."""
        import json
        
        with app.app_context():
            note = Note(
                note_id=sample_note_data['note_id'],
                user_id=sample_note_data['user_id'],
                image_list=json.dumps(sample_note_data['image_list']),
            )
            db.session.add(note)
            db.session.commit()
            
            images = note.get_image_list()
            
            assert isinstance(images, list)
            assert len(images) == 1
