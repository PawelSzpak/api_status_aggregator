import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timezone

from infrastructure.providers.stripe_provider import StripeProvider
from domain import StatusLevel, ServiceCategory, ServiceStatus, IncidentReport

class TestStripeProvider(unittest.TestCase):
    """Test cases for the Stripe status provider."""
    
    def setUp(self):
        """Set up the test environment."""
        self.provider = StripeProvider()
        
        # Sample response data
        self.status_response = {
            "page": {
                "id": "stripe_status",
                "name": "Stripe Status",
                "url": "https://status.stripe.com",
                "updated_at": "2025-03-29T00:00:00Z"
            },
            "status": {
                "indicator": "none",
                "description": "All Systems Operational"
            }
        }
        
        self.components_response = {
            "page": {
                "id": "stripe_status"
            },
            "components": [
                {
                    "id": "api",
                    "name": "API",
                    "status": "operational"
                },
                {
                    "id": "dashboard",
                    "name": "Dashboard",
                    "status": "operational"
                },
                {
                    "id": "checkout",
                    "name": "Checkout",
                    "status": "operational"
                }
            ]
        }
        
        self.incidents_response = {
            "page": {
                "id": "stripe_status"
            },
            "incidents": [
                {
                    "id": "incident-1",
                    "name": "API Latency Issues",
                    "status": "investigating",
                    "impact": "minor",
                    "started_at": "2025-03-29T01:00:00Z",
                    "resolved_at": None,
                    "components": ["api"],
                    "incident_updates": [
                        {
                            "id": "update-1",
                            "body": "We're investigating increased API latency.",
                            "created_at": "2025-03-29T01:05:00Z"
                        }
                    ]
                },
                {
                    "id": "incident-2",
                    "name": "Previous Dashboard Issue",
                    "status": "resolved",
                    "impact": "major",
                    "started_at": "2025-03-28T14:00:00Z",
                    "resolved_at": "2025-03-28T16:00:00Z",
                    "components": ["dashboard"],
                    "incident_updates": [
                        {
                            "id": "update-2",
                            "body": "The dashboard issue has been resolved.",
                            "created_at": "2025-03-28T16:00:00Z"
                        }
                    ]
                }
            ]
        }
    
    @patch('requests.get')
    def test_get_status_operational(self, mock_get):
        """Test getting the current status when all systems are operational."""
        # Configure the mock to return sample responses
        mock_responses = {
            f"{StripeProvider.BASE_URL}{StripeProvider.STATUS_ENDPOINT}": MagicMock(
                json=MagicMock(return_value=self.status_response)
            ),
            f"{StripeProvider.BASE_URL}{StripeProvider.INCIDENTS_ENDPOINT}": MagicMock(
                json=MagicMock(return_value={"incidents": []})
            )
        }
        
        mock_get.side_effect = lambda url, **kwargs: mock_responses.get(url)
        
        # Call the method under test
        status = self.provider.get_status()
        
        # Verify the status
        self.assertEqual(status.provider_name, "Stripe")
        self.assertEqual(status.category, ServiceCategory.PAYMENT)
        self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
        self.assertIn("operational", status.message.lower())
    
    @patch('requests.get')
    def test_get_status_with_incidents(self, mock_get):
        """Test getting the current status with active incidents."""
        # Configure the mock to return sample responses
        mock_responses = {
            f"{StripeProvider.BASE_URL}{StripeProvider.STATUS_ENDPOINT}": MagicMock(
                json=MagicMock(return_value=self.status_response)
            ),
            f"{StripeProvider.BASE_URL}{StripeProvider.INCIDENTS_ENDPOINT}": MagicMock(
                json=MagicMock(return_value=self.incidents_response)
            )
        }
        
        mock_get.side_effect = lambda url, **kwargs: mock_responses.get(url)
        
        # Call the method under test
        status = self.provider.get_status()
        
        # Verify the status - should be DEGRADED due to "minor" incident
        self.assertEqual(status.provider_name, "Stripe")
        self.assertEqual(status.status_level, StatusLevel.DEGRADED)
        self.assertIn("API Latency Issues", status.message)
    
    @patch('requests.get')
    def test_get_incidents(self, mock_get):
        """Test getting active incidents."""
        # Configure the mock to return sample response
        mock_response = MagicMock()
        mock_response.json.return_value = self.incidents_response
        mock_get.return_value = mock_response
        
        # Call the method under test
        incidents = self.provider.get_incidents()
        
        # Only unresolved incidents should be returned
        self.assertEqual(len(incidents), 1)
        
        # Verify incident details
        incident = incidents[0]
        self.assertEqual(incident.id, "incident-1")
        self.assertEqual(incident.provider_name, "Stripe")
        self.assertEqual(incident.title, "API Latency Issues")
        # Check status_level instead of status
        self.assertEqual(incident.status_level, StatusLevel.DEGRADED)
        self.assertIsNotNone(incident.started_at)
        self.assertIsNone(incident.resolved_at)
        # Check if the description contains expected content
        self.assertIn("investigating", incident.description.lower())
    
    @patch('requests.get')
    def test_get_component_statuses(self, mock_get):
        """Test getting component statuses."""
        # Configure the mock to return sample response
        mock_response = MagicMock()
        mock_response.json.return_value = self.components_response
        mock_get.return_value = mock_response
        
        # Call the method under test
        statuses = self.provider.get_component_statuses()
        
        # Verify the component statuses
        self.assertEqual(len(statuses), 3)  # Three components in our sample
        
        # All components should be operational
        for status in statuses:
            self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
            self.assertEqual(status.category, ServiceCategory.PAYMENT)
            self.assertIn("Component", status.message)
    
    @patch('requests.get')
    def test_error_handling(self, mock_get):
        """Test error handling when API requests fail."""
        # Configure the mock to raise an exception for status endpoint
        mock_get.side_effect = Exception("API error")
        
        # Set a last known status to test fallback
        self.provider._last_status = ServiceStatus(
            provider_name="Stripe",
            category=ServiceCategory.PAYMENT,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All systems operational"
        )
        
        # Call the method under test
        status = self.provider.get_status()
        
        # Verify we get the last known status
        self.assertEqual(status, self.provider._last_status)
    
    @patch('infrastructure.providers.stripe_provider.StripeProvider._fetch_current_status')
    @patch('time.sleep')
    def test_rate_limiting(self, mock_sleep, mock_fetch):
        """Test that rate limiting is applied."""
        # Set up the mock to return a valid status
        mock_fetch.return_value = ServiceStatus(
            provider_name="Stripe",
            category=ServiceCategory.PAYMENT,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All systems operational"
        )
        
        # Call get_status multiple times, but break if sleep is called
        for _ in range(15):
            self.provider.get_status()
            if mock_sleep.called:
                break
        
        # Verify _fetch_current_status was called only up to rate limit
        self.assertLessEqual(mock_fetch.call_count, 12)
        
        # If the limit was reached, verify sleep was called
        if mock_fetch.call_count >= 12:
            mock_sleep.assert_called()
    
    @patch('requests.get')
    def test_get_affected_components(self, mock_get):
        """Test extracting affected components from an incident."""
        # Configure the mock for components endpoint
        mock_response = MagicMock()
        mock_response.json.return_value = self.components_response
        mock_get.return_value = mock_response
        
        # Create a test incident with component references
        incident = {"components": ["api", "dashboard"]}
        
        # Call the method
        components = self.provider._get_affected_components(incident)
        
        # Verify the results
        self.assertEqual(len(components), 2)
        self.assertIn("API", components)
        self.assertIn("Dashboard", components)

if __name__ == '__main__':
    unittest.main()