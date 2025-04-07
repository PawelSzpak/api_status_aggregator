import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

from domain import StatusLevel, ServiceCategory, ServiceStatus, IncidentReport
from infrastructure.providers.okta_provider import OktaStatusProvider

class TestOktaStatusProvider(unittest.TestCase):
    """Tests for the OktaStatusProvider implementation."""
    
    def setUp(self):
        """Set up test fixture."""
        self.provider = OktaStatusProvider()
        
        # Sample HTML response with embedded JSON
        self.mock_html = """
        <html>
        <body>
            <span id="j_id0:j_id8:StringJSON">
                [
                    {
                        "Id": "a9C4z000001BZakEAG",
                        "Status__c": "Resolved",
                        "Category__c": "Service Disruption",
                        "Incident_Title__c": "Workflows issue",
                        "Start_Time__c": "2024-08-08T22:17:00.000+0000",
                        "End_Time__c": "2024-08-08T23:14:00.000+0000",
                        "Log__c": "Our Workflows team is investigating the issue."
                    },
                    {
                        "Id": "a9C4z000001BZecEAG",
                        "Status__c": "Investigating",
                        "Category__c": "Service Disruption",
                        "Incident_Title__c": "Paylocity Import Issue",
                        "Start_Time__c": "2024-11-19T19:56:00.000+0000",
                        "Log__c": "At 8:40am on November 19th PST, the OIN team became aware of an Import issue."
                    }
                ]
            </span>
            <span id="j_id0:j_id8:UptimeJSON">
                [
                    {"year":2024, "uptime":99.99, "month":["100.000","100.000","100.000","100.000","100.000","100.000","100.000","100.000","100.000","100.000","100.000","99.825"]},
                    {"year":2025, "uptime":99.99, "month":["100.000","100.000","100.000","","","","","","","","",""]}
                ]
            </span>
        </body>
        </html>
        """
        
    @patch('requests.get')
    def test_fetch_status_data(self, mock_get):
        """Test fetching status data from the Okta status page."""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.text = self.mock_html
        mock_get.return_value = mock_response
        
        # Call the method
        data = self.provider._fetch_status_data()
        
        # Verify the request was made correctly
        mock_get.assert_called_once_with(
            'https://status.okta.com',
            headers=self.provider.headers,
            timeout=15
        )
        
        # Verify the data was parsed correctly
        self.assertIn('incidents', data)
        self.assertEqual(len(data['incidents']), 2)
        self.assertIn('uptime', data)
        self.assertEqual(len(data['uptime']), 2)
    
    @patch('requests.get')
    def test_get_status_operational(self, mock_get):
        """Test getting status when everything is operational."""
        # Configure mock response with no active incidents
        html = self.mock_html.replace('"Status__c": "Investigating"', '"Status__c": "Resolved"')
        mock_response = MagicMock()
        mock_response.text = html
        mock_get.return_value = mock_response
        
        # Call the method
        status = self.provider.get_status()
        
        # Verify the status is operational
        self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
        self.assertEqual(status.category, ServiceCategory.AUTHENTICATION)
        self.assertEqual(status.provider_name, "Okta")
        self.assertIn("operational", status.message.lower())
    
    @patch('requests.get')
    def test_get_status_outage(self, mock_get):
        """Test getting status when there's an outage."""
        # Configure mock response with active major incident
        mock_response = MagicMock()
        mock_response.text = self.mock_html
        mock_get.return_value = mock_response
        
        # Call the method
        status = self.provider.get_status()
        
        # Verify the status is outage
        self.assertEqual(status.status_level, StatusLevel.OUTAGE)
        self.assertIn("experiencing issues", status.message.lower())
    
    @patch('requests.get')
    def test_get_incidents(self, mock_get):
        """Test fetching active incidents."""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.text = self.mock_html
        mock_get.return_value = mock_response
        
        # Call the method
        incidents = self.provider.get_incidents()
        
        # Verify incidents are parsed correctly
        self.assertGreaterEqual(len(incidents), 1)  # At least one incident
        
        # Find the active incident
        active_incident = next((i for i in incidents if i.id == "a9C4z000001BZecEAG"), None)
        self.assertIsNotNone(active_incident, "Active incident should be present")
        if active_incident:
            self.assertEqual(active_incident.provider_name, "Okta")
            self.assertEqual(active_incident.title, "Paylocity Import Issue")
    
    @patch('requests.get')
    def test_error_handling(self, mock_get):
        """Test error handling when the request fails."""
        # Configure mock to raise an exception
        mock_get.side_effect = Exception("Connection error")
        
        # Set a last known status
        self.provider._last_status = ServiceStatus(
            provider_name="Okta",
            category=ServiceCategory.AUTHENTICATION,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All systems operational"
        )
        
        # Call the method
        status = self.provider.get_status()
        
        # Verify we get the cached status
        self.assertEqual(status, self.provider._last_status)
    
    def test_parse_datetime(self):
        """Test parsing various datetime formats."""
        # Test valid formats
        dt1 = self.provider._parse_datetime("2024-11-19T19:56:00.000+0000")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2024)
        self.assertEqual(dt1.month, 11)
        self.assertEqual(dt1.day, 19)
        
        # Test Z format
        dt2 = self.provider._parse_datetime("2024-11-19T19:56:00.000Z")
        self.assertIsNotNone(dt2)
        
        # Test invalid format
        dt3 = self.provider._parse_datetime("invalid")
        self.assertIsNone(dt3)
        
        # Test None
        dt4 = self.provider._parse_datetime(None)
        self.assertIsNone(dt4)
    
    @patch('infrastructure.providers.okta_provider.OktaStatusProvider._fetch_current_status')
    @patch('time.sleep')
    def test_rate_limiting(self, mock_sleep, mock_fetch):
        """Test that rate limiting is applied."""
        # Set up mock to return a status
        mock_fetch.return_value = ServiceStatus(
            provider_name="Okta",
            category=ServiceCategory.AUTHENTICATION,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All systems operational"
        )
        
        # Call get_status multiple times, but stop if sleep is called
        for _ in range(12):  # More than the rate limit of 12
            self.provider.get_status()
            if mock_sleep.called:
                break
        
        # Verify fetch was not called more than the rate limit
        self.assertLessEqual(mock_fetch.call_count, 12)
        
        # If the limit was reached, verify sleep was called
        if mock_fetch.call_count >= 12:
            mock_sleep.assert_called()
    
    @patch('requests.get')
    def test_caching(self, mock_get):
        """Test that status data is cached."""
        # Configure mock response
        mock_response = MagicMock()
        mock_response.text = self.mock_html
        mock_get.return_value = mock_response
        
        # Call _fetch_status_data twice
        data1 = self.provider._fetch_status_data()
        data2 = self.provider._fetch_status_data()
        
        # Verify the request was made only once
        mock_get.assert_called_once()
        
        # Verify both calls returned the same data
        self.assertEqual(data1, data2)

if __name__ == '__main__':
    unittest.main()