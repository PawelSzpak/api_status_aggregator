import unittest
from unittest.mock import patch, MagicMock
import json
import re
from datetime import datetime, timezone

from domain import ProviderConfiguration, StatusLevel
from infrastructure.providers.auth0 import Auth0StatusProvider

class TestAuth0StatusProvider(unittest.TestCase):
    """Test cases for the Auth0StatusProvider implementation."""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.config = ProviderConfiguration(
            name="Auth0",
            category="auth",
            status_url="https://status.auth0.com",
            rate_limit=5,
            check_interval=300
        )
        self.provider = Auth0StatusProvider(self.config)
        
        # Load sample data from fixture
        with open('tests/fixtures/auth0_status_data.json', 'r') as f:
            self.sample_data = json.load(f)
    
    @patch('infrastructure.providers.auth0.requests.get')
    def test_fetch_current_status_operational(self, mock_get):
        """Test fetching current status when all services are operational."""
        # Modify sample data to have no incidents
        test_data = self._create_mock_next_data({
            "activeIncidents": [
                {
                    "region": "US-1",
                    "response": {
                        "uptime": "99.999%+",
                        "incidents": []
                    }
                }
            ]
        })
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = test_data
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method
        status = self.provider.fetch_current_status()
        
        # Verify the results
        self.assertEqual(status.provider, "Auth0")
        self.assertEqual(status.category, "auth")
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertEqual(status.message, "All Auth0 services are operational.")
    
    @patch('infrastructure.providers.auth0.requests.get')
    def test_fetch_current_status_degraded(self, mock_get):
        """Test fetching current status when some services are degraded."""
        # Modify sample data to have one region with incidents
        test_data = self._create_mock_next_data({
            "activeIncidents": [
                {
                    "region": "US-1",
                    "response": {
                        "uptime": "99.9%",
                        "incidents": [
                            {
                                "id": "test-incident",
                                "name": "Test Incident",
                                "status": "investigating",
                                "impact": "minor",
                                "updated_at": "2025-03-03T00:00:00Z",
                                "incident_updates": [
                                    {
                                        "body": "We are investigating authentication issues.",
                                        "created_at": "2025-03-03T00:00:00Z"
                                    }
                                ]
                            }
                        ]
                    }
                },
                {
                    "region": "US-2",
                    "response": {
                        "uptime": "99.999%+",
                        "incidents": []
                    }
                }
            ]
        })
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = test_data
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method
        status = self.provider.fetch_current_status()
        
        # Verify the results
        self.assertEqual(status.provider, "Auth0")
        self.assertEqual(status.category, "auth")
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("US-1", status.message)
        self.assertIn("MINOR", status.message)
    
    @patch('infrastructure.providers.auth0.requests.get')
    def test_fetch_current_status_outage(self, mock_get):
        """Test fetching current status during major outage."""
        # Modify sample data to have multiple regions with incidents
        test_data = self._create_mock_next_data({
            "activeIncidents": [
                {
                    "region": "US-1",
                    "response": {
                        "uptime": "98.5%",
                        "incidents": [
                            {
                                "id": "test-incident-1",
                                "name": "Test Incident 1",
                                "status": "investigating",
                                "impact": "major",
                                "updated_at": "2025-03-03T00:00:00Z",
                                "incident_updates": [
                                    {
                                        "body": "Authentication services are down.",
                                        "created_at": "2025-03-03T00:00:00Z"
                                    }
                                ]
                            }
                        ]
                    }
                },
                {
                    "region": "US-2",
                    "response": {
                        "uptime": "99.0%",
                        "incidents": [
                            {
                                "id": "test-incident-2",
                                "name": "Test Incident 2",
                                "status": "investigating",
                                "impact": "critical",
                                "updated_at": "2025-03-03T00:10:00Z",
                                "incident_updates": [
                                    {
                                        "body": "All services are experiencing disruption.",
                                        "created_at": "2025-03-03T00:10:00Z"
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        })
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = test_data
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method
        status = self.provider.fetch_current_status()
        
        # Verify the results
        self.assertEqual(status.provider, "Auth0")
        self.assertEqual(status.category, "auth")
        self.assertEqual(status.status, StatusLevel.OUTAGE)
        self.assertIn("CRITICAL", status.message)
    
    @patch('infrastructure.providers.auth0.requests.get')
    def test_fetch_active_incidents(self, mock_get):
        """Test fetching active incidents."""
        # Use sample data
        test_data = self._create_mock_next_data({
            "activeIncidents": [
                {
                    "region": "US-1",
                    "response": {
                        "uptime": "99.9%",
                        "incidents": [
                            {
                                "id": "incident-1",
                                "name": "Authentication Issues",
                                "status": "investigating",
                                "impact": "major",
                                "created_at": "2025-03-03T00:00:00Z",
                                "updated_at": "2025-03-03T00:15:00Z",
                                "incident_updates": [
                                    {
                                        "body": "We are investigating authentication failures.",
                                        "created_at": "2025-03-03T00:15:00Z",
                                        "affected_components": [
                                            {"name": "Authentication API"},
                                            {"name": "Management API"}
                                        ]
                                    },
                                    {
                                        "body": "Issue identified.",
                                        "created_at": "2025-03-03T00:05:00Z",
                                        "affected_components": [
                                            {"name": "Authentication API"}
                                        ]
                                    }
                                ]
                            },
                            {
                                "id": "incident-2",
                                "name": "Dashboard Slowness",
                                "status": "resolved",
                                "impact": "minor",
                                "created_at": "2025-03-02T12:00:00Z",
                                "updated_at": "2025-03-02T15:00:00Z",
                                "incident_updates": [
                                    {
                                        "body": "The issue has been resolved.",
                                        "created_at": "2025-03-02T15:00:00Z",
                                        "affected_components": [
                                            {"name": "Dashboard"}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        })
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = test_data
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method
        incidents = self.provider.fetch_active_incidents()
        
        # Verify the results
        self.assertEqual(len(incidents), 1)  # Only the non-resolved incident
        incident = incidents[0]
        self.assertEqual(incident.id, "incident-1")
        self.assertEqual(incident.provider, "Auth0")
        self.assertEqual(incident.title, "Authentication Issues")
        self.assertEqual(incident.status, "investigating")
        self.assertEqual(incident.impact, "major")
        self.assertEqual(incident.region, "US-1")
        self.assertEqual(incident.affected_components, ["Authentication API", "Management API"])
        self.assertEqual(incident.message, "We are investigating authentication failures.")
    
    @patch('infrastructure.providers.auth0.requests.get')
    def test_connection_error_handling(self, mock_get):
        """Test handling of connection errors."""
        # Mock a request exception
        mock_get.side_effect = Exception("Connection failed")
        
        # Verify exception is properly raised
        with self.assertRaises(ConnectionError):
            self.provider.fetch_current_status()
    
    def _create_mock_next_data(self, data):
        """Create a mock __NEXT_DATA__ HTML response."""
        next_data = {
            "props": {
                "pageProps": data
            }
        }
        return f'<html><head></head><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></body></html>'

if __name__ == '__main__':
    unittest.main()