import unittest
from unittest.mock import patch, MagicMock
import requests
import os
from datetime import datetime
from bs4 import BeautifulSoup

from infrastructure.providers.square_provider import SquareProvider
from domain.enums import StatusLevel
from domain.models import ServiceStatus

#Concerned about the non operation HTML imports. Only the operational one exists, however further down it tries
#to edit status by editing "operation" with "degrated" in a response. Are these 2 different tests, or is it not using the same thing 
#consistently?

class TestSquareProvider(unittest.TestCase):
    def setUp(self):
        self.provider = SquareProvider()
        
        # Load the test HTML files
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Load the all-operational HTML sample
        with open(os.path.join(current_dir, 'fixtures/square_all_operational.html'), 'r', encoding='utf-8') as f:
            self.all_operational_html = f.read()
            
        # Load HTML with one region having issues
        with open(os.path.join(current_dir, 'fixtures/square_one_region_issue.html'), 'r', encoding='utf-8') as f:
            self.one_region_issue_html = f.read()
            
        # Load HTML with multiple regions having issues
        with open(os.path.join(current_dir, 'fixtures/square_multiple_issues.html'), 'r', encoding='utf-8') as f:
            self.multiple_issues_html = f.read()

    def test_init(self):
        """Test initialization of the SquareProvider"""
        self.assertEqual(self.provider.name, "Square")
        self.assertEqual(self.provider.category, "payment")
        self.assertEqual(self.provider.status_url, "https://www.issquareup.com/?forceParent=true")

    @patch('requests.get')
    def test_all_regions_operational(self, mock_get):
        """Test parsing when all regions are operational"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = self.all_operational_html
        mock_get.return_value = mock_response
        
        # Get status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertEqual(status.provider, "Square")
        self.assertEqual(status.category, "payment")
        self.assertIn("All Square services are operational", status.message)
        
        # Verify the request was made with the correct URL
        mock_get.assert_called_once_with(self.provider.status_url, timeout=10)

    @patch('requests.get')
    def test_one_region_with_issue(self, mock_get):
        """Test parsing when one region has an issue"""
        # For this test, we'll modify the HTML to simulate an issue in one region
        html = self.all_operational_html.replace(
            'text-icon-operational">',
            'text-icon-degraded">',
            1  # Replace only the first occurrence to simulate a single region with issues
        )
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = html
        mock_get.return_value = mock_response
        
        # Get status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("experiencing issues", status.message)

    @patch('requests.get')
    def test_multiple_regions_with_issues(self, mock_get):
        """Test parsing when multiple regions have issues"""
        # Modify the HTML to simulate issues in multiple regions
        html = self.all_operational_html.replace(
            'text-icon-operational">',
            'text-icon-degraded">',
            3  # Replace three occurrences
        )
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.text = html
        mock_get.return_value = mock_response
        
        # Get status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("experiencing issues", status.message)
        # We should see multiple regions in the message
        self.assertIn("regions", status.message)

    @patch('requests.get')
    def test_connection_error(self, mock_get):
        """Test handling of connection errors"""
        # Mock a connection error
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        # Get status
        status = self.provider.get_status()
        
        # Should fall back to assuming operational when there's an error
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertIn("Unable to determine", status.message)

    @patch('requests.get')
    def test_html_parsing_error(self, mock_get):
        """Test handling of HTML parsing errors"""
        # Mock a malformed HTML response
        mock_response = MagicMock()
        mock_response.text = "<html>Malformed HTML"
        mock_get.return_value = mock_response
        
        # Get status (shouldn't raise an exception)
        status = self.provider.get_status()
        
        # Should handle error gracefully
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertIn("Unable to determine", status.message)

    @patch('requests.get')
    def test_cached_status_on_error(self, mock_get):
        """Test that we use cached status when there's an error and we have previous status"""
        # First, set up a successful call to cache a status
        mock_response = MagicMock()
        mock_response.text = self.all_operational_html
        mock_get.return_value = mock_response
        
        # Call get_status to cache it
        self.provider.get_status()
        
        # Now, simulate an error on the next call
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        # Get status again
        status = self.provider.get_status()
        
        # Should use the cached status
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertIn("from cached status", status.message)

    def test_extract_status_from_icon_class(self):
        """Test the helper method to extract status level from icon class"""
        # Create a method to test the extraction logic directly
        def extract_status(icon_class):
            soup = BeautifulSoup(f'<svg class="{icon_class}"></svg>', 'html.parser')
            svg = soup.find('svg')
            return self.provider._extract_status_from_icon(svg)
        
        # Test various icon classes
        self.assertEqual(extract_status("text-icon-operational"), StatusLevel.OPERATIONAL)
        self.assertEqual(extract_status("text-icon-degraded"), StatusLevel.DEGRADED)
        self.assertEqual(extract_status("text-icon-full-outage"), StatusLevel.OUTAGE)
        self.assertEqual(extract_status("text-icon-partial-outage"), StatusLevel.DEGRADED)
        self.assertEqual(extract_status("text-icon-under-maintenance"), StatusLevel.MAINTENANCE)
        
        # Test default case
        self.assertEqual(extract_status("unknown-class"), StatusLevel.OPERATIONAL)

    def test_rate_limiting(self):
        """Test that rate limiting is applied correctly"""
        # This would be integration testing in a real scenario, but for unit tests
        # we just verify the decorator is applied to the right methods
        from inspect import getmembers, ismethod
        
        # Check if get_status method is decorated with rate_limit
        for name, method in getmembers(self.provider, predicate=ismethod):
            if name == 'get_status':
                # Check if it has the wrapper attribute set by decorator
                self.assertTrue(hasattr(method, '__wrapped__'), 
                               "get_status method should be decorated with rate_limit")

if __name__ == '__main__':
    unittest.main()