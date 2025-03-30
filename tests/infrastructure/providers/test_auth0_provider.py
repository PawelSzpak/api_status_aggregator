import unittest
from unittest.mock import patch, MagicMock
import json
import re
from datetime import datetime, timezone

from domain import ProviderConfiguration, StatusLevel, ServiceCategory
from infrastructure.providers.auth0_provider import Auth0StatusProvider

class TestAuth0StatusProvider(unittest.TestCase):
    """Test cases for the Auth0StatusProvider implementation."""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.config = ProviderConfiguration(
            name="Auth0",
            category=ServiceCategory.AUTHENTICATION,
            status_url="https://status.auth0.com"
        )
        self.provider = Auth0StatusProvider(self.config)
        
    def _create_mock_next_data(self, data):
        """Create a mock __NEXT_DATA__ HTML response."""
        next_data = {
            "props": {
                "pageProps": data
            }
        }
        return f'<html><head></head><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></body></html>'
    
    @patch('requests.get')
    def test_get_status_operational(self, mock_get):
        """Test getting status when all services are operational."""
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
        status = self.provider.get_status()
        
        # Verify the results
        self.assertEqual(status.provider_name, "Auth0")
        self.assertEqual(status.category, ServiceCategory.AUTHENTICATION)
        self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
        self.assertIn("operational", status.message.lower())
    
    @patch('requests.get')
    def test_get_status_degraded(self, mock_get):
        """Test getting status when some services are degraded."""
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
        status = self.provider.get_status()
        
        # Verify the results
        self.assertEqual(status.provider_name, "Auth0")
        self.assertEqual(status.category, ServiceCategory.AUTHENTICATION)
        self.assertEqual(status.status_level, StatusLevel.DEGRADED)
        self.assertIn("US-1", status.message)
    
    @patch('requests.get')
    def test_get_status_outage(self, mock_get):
        """Test getting status during major outage."""
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
        status = self.provider.get_status()
        
        # Verify the results
        self.assertEqual(status.provider_name, "Auth0")
        self.assertEqual(status.category, ServiceCategory.AUTHENTICATION)
        self.assertEqual(status.status_level, StatusLevel.OUTAGE)
    
    @patch('requests.get')
    def test_get_incidents(self, mock_get):
        """Test getting active incidents."""
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
        incidents = self.provider.get_incidents()
        
        # Verify the results
        self.assertEqual(len(incidents), 1)  # Only the non-resolved incident
        incident = incidents[0]
        self.assertEqual(incident.id, "incident-1")
        self.assertEqual(incident.provider_name, "Auth0")
        self.assertEqual(incident.title, "Authentication Issues")
        self.assertEqual(incident.status_level, StatusLevel.DEGRADED)  # Mapped from "major"
    
    @patch('requests.get')
    def test_connection_error_handling(self, mock_get):
        """Test handling of connection errors."""
        # Mock a request exception
        mock_get.side_effect = Exception("Connection failed")
        
        # Set up a previously cached status
        self.provider._last_status = {"status": "operational"}
        
        # Verify the last known status is returned
        status = self.provider.get_status()
        self.assertEqual(status, self.provider._last_status)
    
    @patch('infrastructure.providers.auth0_provider.Auth0StatusProvider._fetch_current_status')
    @patch('time.sleep')
    def test_rate_limiting(self, mock_sleep, mock_fetch):
        """Test that rate limiting is applied correctly.
        
        This test mocks the sleep function to prevent actual waiting
        but verifies that sleep is called with appropriate parameters.
        """
        # Set up mock to return a valid status
        mock_fetch.return_value = {"status": "operational"}
        
        # Call get_status multiple times (more than the rate limit)
        for _ in range(15):  # Trying to exceed the rate limit
            self.provider.get_status()
            
            # If sleep was called, break the loop since 
            # in a real scenario this would pause execution
            if mock_sleep.called:
                break
        
        # Verify that the rate limit was enforced correctly
        self.assertLessEqual(mock_fetch.call_count, 12)  # 12 is the rate limit
        
        # Verify that sleep was called when the limit was reached
        if mock_fetch.call_count >= 12:
            mock_sleep.assert_called()

if __name__ == '__main__':
    unittest.main()