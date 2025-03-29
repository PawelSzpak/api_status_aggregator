import unittest
from unittest.mock import patch, MagicMock
import requests
import json
from datetime import datetime, timezone

from infrastructure.providers.aws_provider import AWSProvider
from domain import StatusLevel, ServiceStatus, ServiceCategory



class TestAWSProvider(unittest.TestCase):
    def setUp(self):
        """Set up fresh AWS provider instance for each test"""
        self.provider = AWSProvider()
        
        # Sample event responses for different scenarios
        self.operational_events = {}
        
        self.degraded_events = {
            "ec2-us-west-1": [
                {
                    "status": "1",  # Active event
                    "event_id": "aws-123456",
                    "event_title": "EC2 API Issues",
                    "start_time": str(int(datetime.now(timezone.utc).timestamp())),
                    "event_log": [
                        {
                            "message": "We are investigating increased API error rates for EC2.",
                            "status": "1",
                            "timestamp": int(datetime.now(timezone.utc).timestamp())
                        }
                    ],
                    "impacted_services": {
                        "ec2-us-west-1": {
                            "service_name": "Amazon EC2",
                            "current": "1",
                            "max": "1"
                        }
                    },
                    "impact": "MAJOR"
                }
            ]
        }
        
        self.outage_events = {
            "s3-us-east-1": [
                {
                    "status": "1",  # Active event
                    "event_id": "aws-234567",
                    "event_title": "S3 Outage",
                    "start_time": str(int(datetime.now(timezone.utc).timestamp())),
                    "event_log": [
                        {
                            "message": "S3 is currently unavailable in the US-EAST-1 region. Complete outage reported.",
                            "status": "1",
                            "timestamp": int(datetime.now(timezone.utc).timestamp())
                        }
                    ],
                    "impacted_services": {
                        "s3-us-east-1": {
                            "service_name": "Amazon S3",
                            "current": "1",
                            "max": "1"
                        }
                    },
                    "impact": "CRITICAL"
                }
            ]
        }
        
        # Sample announcements
        self.empty_announcement = {}
        self.maintenance_announcement = {
            "description": "We will be performing scheduled maintenance on EC2 instances tonight."
        }

    def test_init(self):
        """Test initialization of the AWSProvider"""
        self.assertEqual(self.provider.config.name, "AWS")
        self.assertEqual(self.provider.config.category, ServiceCategory.CLOUD)
        self.assertEqual(self.provider.config.status_url, "https://health.aws.amazon.com/health/status")

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
        self.assertEqual(status.provider_name, "AWS")
        self.assertEqual(status.category, ServiceCategory.CLOUD)
        self.assertEqual(status.status_level, StatusLevel.OPERATIONAL)
        self.assertIn("operating normally", status.message.lower())
        
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
        self.assertEqual(status.provider_name, "AWS")
        self.assertEqual(status.status_level, StatusLevel.DEGRADED)
        self.assertIn("Amazon EC2", status.message)
        self.assertIn("increased API error rates", status.message)

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
        self.assertEqual(status.provider_name, "AWS")
        self.assertEqual(status.status_level, StatusLevel.OUTAGE)
        self.assertIn("Amazon S3", status.message)
        self.assertIn("outage", status.message.lower())

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
        self.assertEqual(status.provider_name, "AWS")
        self.assertEqual(status.status_level, StatusLevel.DEGRADED)
        self.assertIn("scheduled maintenance", status.message)

    @patch('requests.get')
    def test_connection_error(self, mock_get):
        """Test graceful degradation when connection fails"""
        # Mock a connection error
        mock_get.side_effect = requests.RequestException("Connection timeout")
        
        # Set a last known status to test fallback
        self.provider._last_status = ServiceStatus(
            provider_name="AWS",
            category=ServiceCategory.CLOUD,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All services operational"
        )
        
        # Get the status
        status = self.provider.get_status()
        
        # Verify we use the last known status
        self.assertEqual(status, self.provider._last_status)

    @patch('requests.get')
    def test_get_incidents(self, mock_get):
        """Test fetching active incidents"""
        # Mock the events response with outage data
        events_response = MagicMock()
        events_response.json.return_value = self.outage_events
        mock_get.return_value = events_response
        
        # Get incidents
        incidents = self.provider.get_incidents()
        
        # Verify incidents
        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident.id, "aws-234567")
        self.assertEqual(incident.provider_name, "AWS")
        self.assertIn("S3", incident.title)
        self.assertEqual(incident.status_level, StatusLevel.OUTAGE)  # Mapped from CRITICAL

    @patch('infrastructure.providers.aws_provider.AWSProvider._fetch_current_status')
    def test_rate_limiting(self, mock_fetch):
        """Test that rate limiting is applied to get_status"""
        # Set up the mock to return a valid status
        mock_fetch.return_value = ServiceStatus(
            provider_name="AWS",
            category=ServiceCategory.CLOUD,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All services operational"
        )
        
        # Call get_status more times than the rate limit allows
        for _ in range(15):  # Rate limit is 12 per minute
            self.provider.get_status()
            
        # Verify _fetch_current_status was not called more than rate limit
        self.assertLessEqual(mock_fetch.call_count, 12)

if __name__ == '__main__':
    unittest.main()