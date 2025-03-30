import unittest
from unittest.mock import patch, MagicMock
import requests
import os
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from infrastructure.providers.square_provider import SquareProvider
from domain import StatusLevel, ServiceStatus, ServiceCategory, IncidentReport

class TestSquareProvider(unittest.TestCase):
    def setUp(self):
        self.provider = SquareProvider()
        
        # Simple HTML test samples
        self.all_operational_html = """
        <html>
            <body>
                <a class="first:rounded-t-md">
                    <div>US Region</div>
                    <svg class="text-icon-operational"></svg>
                </a>
                <a class="first:rounded-t-md">
                    <div>Europe Region</div>
                    <svg class="text-icon-operational"></svg>
                </a>
                <a class="first:rounded-t-md">
                    <div>Japan Region</div>
                    <svg class="text-icon-operational"></svg>
                </a>
            </body>
        </html>
        """
        
        self.one_region_issue_html = """
        <html>
            <body>
                <a class="first:rounded-t-md" href="/us">
                    <div>US Region</div>
                    <svg class="text-icon-degraded"></svg>
                </a>
                <a class="first:rounded-t-md">
                    <div>Europe Region</div>
                    <svg class="text-icon-operational"></svg>
                </a>
                <a class="first:rounded-t-md">
                    <div>Japan Region</div>
                    <svg class="text-icon-operational"></svg>
                </a>
            </body>
        </html>
        """
        
        self.us_region_detail_html = """
        <html>
            <body>
                <div class="incident-entry">
                    <h3 class="incident-title">Payment Processing Delays</h3>
                    <span class="incident-status">investigating</span>
                    <div class="incident-message">We are investigating reports of payment processing delays.</div>
                </div>
            </body>
        </html>
        """

    def test_init(self):
        """Test initialization of the SquareProvider"""
        self.assertEqual(self.provider.config.name, "Square")
        self.assertEqual(self.provider.config.category, ServiceCategory.PAYMENT)
        self.assertEqual(self.provider.config.status_url, "https://www.issquareup.com/?forceParent=true")

    @patch('requests.get')
    def test_get_status_all_regions_operational(self, mock_get):
        """Test getting status when all regions are operational"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = self.all_operational_html
        mock_get.return_value = mock_response
        
        # Get status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
        self.assertEqual(status.provider_name, "Square")
        self.assertEqual(status.category, ServiceCategory.PAYMENT)
        self.assertIn("operational", status.message.lower())
        
        # Verify the request was made with the correct URL
        mock_get.assert_called_once_with(self.provider.config.status_url, timeout=10)

    @patch('requests.get')
    def test_get_status_one_region_with_issue(self, mock_get):
        """Test getting status when one region has an issue"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = self.one_region_issue_html
        mock_get.return_value = mock_response
        
        # Get status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.status_level, StatusLevel.DEGRADED)
        self.assertIn("experiencing issues", status.message.lower())
        self.assertIn("US Region", status.message)

    @patch('requests.get')
    def test_get_incidents(self, mock_get):
        """Test getting incidents"""
        # Set up mock to handle multiple calls
        mock_get.side_effect = lambda url, **kwargs: {
            "https://www.issquareup.com/?forceParent=true": MagicMock(text=self.one_region_issue_html),
            "https://www.issquareup.com/us": MagicMock(text=self.us_region_detail_html)
        }.get(url)
        
        # Get incidents
        incidents = self.provider.get_incidents()
        
        # Assertions
        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident.provider_name, "Square")
        self.assertEqual(incident.title, "Payment Processing Delays")
        self.assertTrue("Payment Processing Delays" in incident.title)
        self.assertTrue("investigating reports" in incident.description.lower())

    @patch('requests.get')
    def test_connection_error_handling(self, mock_get):
        """Test handling of connection errors"""
        # Mock a connection error
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        # Set a last known status to test fallback
        self.provider._last_status = ServiceStatus(
            provider_name="Square",
            category=ServiceCategory.PAYMENT,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All Square services are operational"
        )
        
        # Get status
        status = self.provider.get_status()
        
        # Should return the cached status
        self.assertEqual(status, self.provider._last_status)

    @patch('requests.get')
    def test_get_detailed_status(self, mock_get):
        """Test getting detailed status for all regions"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = self.one_region_issue_html
        mock_get.return_value = mock_response
        
        # Get detailed status
        region_statuses = self.provider.get_detailed_status()
        
        # Assertions
        self.assertEqual(len(region_statuses), 3)  # Three regions in our test HTML
        
        # US region should be degraded
        us_status = region_statuses.get("US Region")
        self.assertIsNotNone(us_status)
        self.assertEqual(us_status.status_level, StatusLevel.DEGRADED)
        
        # Europe region should be operational
        europe_status = region_statuses.get("Europe Region")
        self.assertIsNotNone(europe_status)
        self.assertEqual(europe_status.status_level, StatusLevel.OPERATIONAL)

    @patch('infrastructure.providers.square_provider.SquareProvider._fetch_current_status')
    @patch('time.sleep')
    def test_rate_limiting(self, mock_sleep, mock_fetch):
        """Test that rate limiting is applied"""
        # Setup mock to return a valid status
        mock_fetch.return_value = ServiceStatus(
            provider_name="Square",
            category=ServiceCategory.PAYMENT,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All Square services are operational"
        )
        
        # Call get_status multiple times, but break if sleep is called
        for _ in range(15):
            self.provider.get_status()
            if mock_sleep.called:
                break
        
        # Verify fetch was called only up to the rate limit
        self.assertLessEqual(mock_fetch.call_count, 12)
        
        # If we reached the limit, verify sleep was called
        if mock_fetch.call_count >= 12:
            mock_sleep.assert_called()

if __name__ == '__main__':
    unittest.main()