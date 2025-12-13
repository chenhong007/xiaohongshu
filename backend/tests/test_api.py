"""
API Tests

Tests for REST API endpoints.
"""
import pytest
import json


class TestHealthCheck:
    """Tests for health check endpoint."""
    
    def test_health_check(self, client):
        """Test health check returns healthy status."""
        response = client.get('/api/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'


class TestAccountsAPI:
    """Tests for accounts API endpoints."""
    
    def test_get_accounts_empty(self, client):
        """Test getting accounts when empty."""
        response = client.get('/api/accounts')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert isinstance(data['data'], list)
    
    def test_add_account(self, client, sample_account_data):
        """Test adding a new account."""
        response = client.post(
            '/api/accounts',
            data=json.dumps(sample_account_data),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['user_id'] == sample_account_data['user_id']
    
    def test_add_account_duplicate(self, client, sample_account_data):
        """Test adding duplicate account returns 409."""
        # Add first time
        client.post(
            '/api/accounts',
            data=json.dumps(sample_account_data),
            content_type='application/json'
        )
        
        # Try to add again
        response = client.post(
            '/api/accounts',
            data=json.dumps(sample_account_data),
            content_type='application/json'
        )
        
        assert response.status_code == 409
    
    def test_add_account_missing_user_id(self, client):
        """Test adding account without user_id fails."""
        response = client.post(
            '/api/accounts',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
    
    def test_get_account_not_found(self, client):
        """Test getting non-existent account."""
        response = client.get('/api/accounts/99999')
        
        assert response.status_code == 404
    
    def test_delete_account(self, client, sample_account_data):
        """Test deleting an account."""
        # Add account
        add_response = client.post(
            '/api/accounts',
            data=json.dumps(sample_account_data),
            content_type='application/json'
        )
        account_id = json.loads(add_response.data)['data']['id']
        
        # Delete account
        response = client.delete(f'/api/accounts/{account_id}')
        
        assert response.status_code == 200
        
        # Verify deleted
        get_response = client.get(f'/api/accounts/{account_id}')
        assert get_response.status_code == 404


class TestAccountsStatusAPI:
    """Tests for lightweight status API."""
    
    def test_get_accounts_status(self, client):
        """Test getting account status."""
        response = client.get('/api/accounts/status')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert isinstance(data['data'], list)
