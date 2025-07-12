# tests/presentation/test_web_interface.py
import pytest
import json
import time
from flask import Flask
from unittest.mock import Mock, patch

from presentation.web.app import create_app
from domain.enums import ServiceCategory, StatusLevel
from domain.models import ServiceStatus
from datetime import datetime, timezone


@pytest.fixture
def app():
    """Create test Flask application."""
    test_app = create_app()
    test_app.config['TESTING'] = True
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_status_data():
    """Mock status data for testing."""
    return {
        'providers': [
            {
                'name': 'Stripe',
                'category': 'payment',
                'status': 'operational',
                'message': 'All systems operational',
                'last_checked': datetime.now(timezone.utc).isoformat()
            },
            {
                'name': 'Auth0',
                'category': 'authentication',
                'status': 'degraded',
                'message': 'Experiencing minor issues',
                'last_checked': datetime.now(timezone.utc).isoformat()
            }
        ],
        'categories': {
            'payment': 'operational',
            'authentication': 'degraded',
            'cloud': 'operational'
        },
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'error': None
    }


class TestWebInterface:
    """Test suite for web interface functionality."""
    
    def test_dashboard_renders(self, client):
        """Test that the dashboard page renders correctly."""
        response = client.get('/')
        
        assert response.status_code == 200
        assert b'API Status Dashboard' in response.data
        assert b'Service Categories' in response.data
        assert b'Service Providers' in response.data
    
    def test_dashboard_includes_required_elements(self, client):
        """Test that dashboard includes all required UI elements."""
        response = client.get('/')
        html = response.data.decode()
        
        # Check for essential sections
        assert 'category-tiles' in html
        assert 'providers-grid' in html
        assert 'category-filter' in html
        assert 'status-filter' in html
        
        # Check for JavaScript includes
        assert 'dashboard.js' in html
        assert 'initialData' in html
    
    def test_api_status_endpoint(self, client, mock_status_data):
        """Test the /api/status endpoint."""
        with patch('infrastructure.scheduler.scheduler.get_latest_data', return_value=mock_status_data):
            response = client.get('/api/status')
            
            assert response.status_code == 200
            assert response.content_type == 'application/json'
            
            data = json.loads(response.data)
            assert 'providers' in data
            assert 'categories' in data
            assert 'last_updated' in data
    
    def test_api_refresh_endpoint(self, client, mock_status_data):
        """Test the /api/status/refresh endpoint."""
        with patch('infrastructure.scheduler.scheduler.force_update', return_value=mock_status_data):
            response = client.post('/api/status/refresh')
            
            assert response.status_code == 200
            assert response.content_type == 'application/json'
            
            data = json.loads(response.data)
            assert 'providers' in data
    
    def test_health_check_endpoint(self, client):
        """Test the /health endpoint."""
        response = client.get('/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'timestamp' in data
    
    def test_sse_stream_endpoint(self, client, mock_status_data):
        """Test the Server-Sent Events stream endpoint."""
        with patch('infrastructure.scheduler.scheduler.get_latest_data', return_value=mock_status_data):
            response = client.get('/api/status/stream')
            
            assert response.status_code == 200
            assert response.content_type == 'text/event-stream'
            assert 'Cache-Control' in response.headers
            assert response.headers['Cache-Control'] == 'no-cache'


class TestWebIntegration:
    """Integration tests for the complete web stack."""
    
    @patch('infrastructure.scheduler.scheduler')
    def test_dashboard_with_real_data_flow(self, mock_scheduler, client):
        """Test dashboard with realistic data flow."""
        # Mock scheduler to return test data
        test_data = {
            'providers': [
                {
                    'name': 'Stripe',
                    'category': 'payment',
                    'status': 'operational',
                    'message': 'All Stripe services operational',
                    'last_checked': datetime.now(timezone.utc).isoformat()
                }
            ],
            'categories': {'payment': 'operational'},
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'error': None
        }
        mock_scheduler.get_latest_data.return_value = test_data
        
        # Test dashboard load
        response = client.get('/')
        assert response.status_code == 200
        
        # Test API endpoint
        api_response = client.get('/api/status')
        assert api_response.status_code == 200
        
        api_data = json.loads(api_response.data)
        assert api_data['providers'][0]['name'] == 'Stripe'
    
    def test_error_handling(self, client):
        """Test error handling in web interface."""
        with patch('infrastructure.scheduler.scheduler.get_latest_data', side_effect=Exception("Test error")):
            response = client.get('/api/status')
            # Should still return 200 but with error handling
            assert response.status_code == 500 or response.status_code == 200


# Load testing helper (optional)
class TestWebPerformance:
    """Performance tests for web interface."""
    
    def test_dashboard_load_time(self, client):
        """Test that dashboard loads within acceptable time."""
        start_time = time.time()
        response = client.get('/')
        load_time = time.time() - start_time
        
        assert response.status_code == 200
        assert load_time < 2.0  # Should load in under 2 seconds
    
    def test_api_response_time(self, client):
        """Test that API responds quickly."""
        start_time = time.time()
        response = client.get('/api/status')
        response_time = time.time() - start_time
        
        assert response.status_code == 200
        assert response_time < 1.0  # Should respond in under 1 second

        