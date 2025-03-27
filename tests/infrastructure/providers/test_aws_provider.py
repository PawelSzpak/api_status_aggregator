import unittest
from unittest.mock import patch, MagicMock
import requests
import json
from datetime import datetime

from infrastructure.providers.aws_provider import AWSProvider
from domain.enums import StatusLevel, ServiceStatus



class TestAWSProvider(unittest.TestCase):
    def setUp(self):
        """Set up fresh AWS provider instance for each test"""
        self.provider = AWSProvider()
        
        # Sample event responses for different scenarios
        self.operational_events = []
        
        self.degraded_events = {
            "ec2-us-west-1": [
                {
                    "status": "1",  # Active event
                    "event_log": [
                        {
                            "message": "We are investigating increased API error rates for EC2.",
                            "status": "1",
                            "timestamp": int(datetime.now().timestamp())
                        }
                    ],
                    "impacted_services": {
                        "ec2-us-west-1": {
                            "service_name": "Amazon EC2",
                            "current": "1",
                            "max": "1"
                        }
                    }
                }
            ]
        }
        
        self.outage_events = {
            "s3-us-east-1": [
                {
                    "status": "1",  # Active event
                    "event_log": [
                        {
                            "message": "S3 is currently unavailable in the US-EAST-1 region. Complete outage reported.",
                            "status": "1",
                            "timestamp": int(datetime.now().timestamp())
                        }
                    ],
                    "impacted_services": {
                        "s3-us-east-1": {
                            "service_name": "Amazon S3",
                            "current": "1",
                            "max": "1"
                        }
                    }
                }
            ]
        }
        
        self.multi_service_events = {
            "us-east-1": [
                {
                    "status": "1",  # Active event
                    "event_log": [
                        {
                            "message": "Multiple services are experiencing issues in US-EAST-1.",
                            "status": "1",
                            "timestamp": int(datetime.now().timestamp())
                        }
                    ],
                    "impacted_services": {
                        "ec2-us-east-1": {
                            "service_name": "Amazon EC2",
                            "current": "1",
                            "max": "1"
                        },
                        "rds-us-east-1": {
                            "service_name": "Amazon RDS",
                            "current": "1",
                            "max": "1"
                        },
                        "s3-us-east-1": {
                            "service_name": "Amazon S3",
                            "current": "1",
                            "max": "1"
                        }
                    }
                }
            ]
        }
        
        # Sample announcements
        self.empty_announcement = {"description": None}
        self.maintenance_announcement = {
            "description": "We will be performing scheduled maintenance on EC2 instances tonight."
        }

    def test_init(self):
        """Test initialization of the AWSProvider"""
        self.assertEqual(self.provider.name, "AWS")
        self.assertEqual(self.provider.category, "cloud")
        self.assertEqual(self.provider.status_url, "https://health.aws.amazon.com/health/status")

    @patch('requests.get')
    def test_all_services_operational(self, mock_get):
        """Test when all AWS services are operational"""
        # Mock responses for both endpoints
        events_response = MagicMock()
        events_response.json.return_value = self.operational_events
        
        announcement_response = MagicMock()
        announcement_response.json.return_value = self.empty_announcement
        
        # Configure the mock to return different responses for different URLs
        mock_get.side_effect = lambda url, **kwargs: {
            "https://health.aws.amazon.com/public/currentevents": events_response,
            "https://health.aws.amazon.com/public/announcement": announcement_response
        }.get(url)
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.category, "cloud")
        self.assertEqual(status.status, StatusLevel.OPERATIONAL)
        self.assertIn("operating normally", status.message)
        
        # Verify both endpoints were called
        self.assertEqual(mock_get.call_count, 2)

    @patch('requests.get')
    def test_service_degradation(self, mock_get):
        """Test when AWS reports service degradation"""
        # Mock the events response
        events_response = MagicMock()
        events_response.json.return_value = self.degraded_events
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = events_response
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("Amazon EC2", status.message)
        self.assertIn("increased API error rates", status.message)
        
        # Verify only the events endpoint was called
        self.assertEqual(mock_get.call_count, 1)

    @patch('requests.get')
    def test_service_outage(self, mock_get):
        """Test when AWS reports a service outage"""
        # Mock the events response
        events_response = MagicMock()
        events_response.json.return_value = self.outage_events
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = events_response
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.OUTAGE)
        self.assertIn("Amazon S3", status.message)
        self.assertIn("outage", status.message.lower())
        
        # Verify only the events endpoint was called
        self.assertEqual(mock_get.call_count, 1)

    @patch('requests.get')
    def test_announcement_only(self, mock_get):
        """Test when AWS has an announcement but no current events"""
        # Mock responses for both endpoints
        events_response = MagicMock()
        events_response.json.return_value = self.operational_events
        
        announcement_response = MagicMock()
        announcement_response.json.return_value = self.maintenance_announcement
        
        # Configure the mock to return different responses for different URLs
        mock_get.side_effect = lambda url, **kwargs: {
            "https://health.aws.amazon.com/public/currentevents": events_response,
            "https://health.aws.amazon.com/public/announcement": announcement_response
        }.get(url)
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("scheduled maintenance", status.message)
        
        # Verify both endpoints were called
        self.assertEqual(mock_get.call_count, 2)

    @patch('requests.get')
    def test_connection_error(self, mock_get):
        """Test graceful degradation when connection fails"""
        # Mock a connection error
        mock_get.side_effect = requests.RequestException("Connection timeout")
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions for error handling
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.UNKNOWN)
        self.assertIn("Unable to fetch", status.message)
        self.assertIn("Connection timeout", status.message)

    @patch('requests.get')
    def test_json_parsing_error(self, mock_get):
        """Test handling of invalid JSON response"""
        # Mock the JSON parsing failure
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions for parsing error handling
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.UNKNOWN)
        self.assertIn("parsing AWS status response", status.message)

    @patch('requests.get')
    def test_multiple_affected_services(self, mock_get):
        """Test when multiple AWS services are affected"""
        # Mock the events response with multiple affected services
        events_response = MagicMock()
        events_response.json.return_value = self.multi_service_events
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = events_response
        
        # Get the status
        status = self.provider.get_status()
        
        # Assertions for multiple services
        self.assertEqual(status.provider, "AWS")
        self.assertEqual(status.status, StatusLevel.DEGRADED)
        self.assertIn("Amazon EC2", status.message)
        self.assertIn("Amazon RDS", status.message)
        self.assertIn("Amazon S3", status.message)

    def test_rate_limiting(self):
        """Test that rate limiting is applied correctly"""
        # Verify the rate_limit decorator is applied to get_status method
        from inspect import getmembers, ismethod
        
        # Check if get_status method is decorated with rate_limit
        for name, method in getmembers(self.provider, predicate=ismethod):
            if name == 'get_status':
                # Check if it has the wrapper attribute set by decorator
                self.assertTrue(hasattr(method, '__wrapped__'), 
                               "get_status method should be decorated with rate_limit")


if __name__ == '__main__':
    unittest.main()