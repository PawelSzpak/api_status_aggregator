import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime

from infrastructure.providers.stripe_provider import StripeProvider
from domain.enums import StatusLevel, ServiceCategory

class TestStripeProvider(unittest.TestCase):
    """Test cases for the Stripe status provider."""
    
    def setUp(self):
        """Set up the test environment."""
        self.provider = StripeProvider()
        
        # Load sample response data
        with open('tests/fixtures/stripe_status.json', 'r') as f:
            self.status_response = json.load(f)
            
        with open('tests/fixtures/stripe_components.json', 'r') as f:
            self.components_response = json.load(f)
            
        with open('tests/fixtures/stripe_incidents.json', 'r') as f:
            self.incidents_response = json.load(f)
    
    @patch('requests.get')
    def test_fetch_current_status(self, mock_get):
        """Test fetching the current status."""
        # Configure the mock to return sample responses
        mock_response = MagicMock()
        mock_response.json.side_effect = [
            self.status_response,
            self.incidents_response
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method under test
        status = self.provider.fetch_current_status()
        
        # Verify the status
        self.assertEqual(status.provider_name, "Stripe")
        self.assertEqual(status.category, ServiceCategory.PAYMENT)
        
        # Check if the status was correctly mapped
        expected_status = StatusLevel.OPERATIONAL
        if "critical" in [i.get("impact") for i in self.incidents_response.get("incidents", [])
                          if i.get("status") != "resolved"]:
            expected_status = StatusLevel.OUTAGE
        elif "major" in [i.get("impact") for i in self.incidents_response.get("incidents", [])
                         if i.get("status") != "resolved"]:
            expected_status = StatusLevel.DEGRADED
            
        self.assertEqual(status.status_level, expected_status)
        
    @patch('requests.get')
    def test_fetch_active_incidents(self, mock_get):
        """Test fetching active incidents."""
        # Configure the mock to return sample response
        mock_response = MagicMock()
        mock_response.json.return_value = self.incidents_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method under test
        incidents = self.provider.fetch_active_incidents()
        
        # Count active incidents in the sample data
        active_count = len([i for i in self.incidents_response.get("incidents", [])
                           if i.get("status") != "resolved"])
        
        # Verify the incidents
        self.assertEqual(len(incidents), active_count)
        
        # Verify incident details if there are any active incidents
        if incidents:
            incident = incidents[0]
            self.assertEqual(incident.provider_name, "Stripe")
            self.assertIsInstance(incident.started_at, datetime)
    
    @patch('requests.get')
    def test_get_component_statuses(self, mock_get):
        """Test fetching component statuses."""
        # Configure the mock to return sample response
        mock_response = MagicMock()
        mock_response.json.return_value = self.components_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Call the method under test
        statuses = self.provider.get_component_statuses()
        
        # Verify the component statuses
        component_count = len(self.components_response.get("components", []))
        self.assertEqual(len(statuses), component_count)
        
        # Check a few components
        if statuses:
            # All components should be in the same category
            self.assertEqual(statuses[0].category, ServiceCategory.PAYMENT)
            
            # Component name should be included in the provider name
            component_name = self.components_response["components"][0]["name"]
            self.assertIn(component_name, statuses[0].provider_name)
    
    @patch('requests.get')
    def test_error_handling(self, mock_get):
        """Test error handling when the API request fails."""
        # Configure the mock to raise an exception
        mock_get.side_effect = Exception("API error")
        
        # Verify that the exception is caught and re-raised
        with self.assertRaises(ConnectionError):
            self.provider.fetch_current_status()

if __name__ == '__main__':
    unittest.main()