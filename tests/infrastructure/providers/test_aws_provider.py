import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime
import requests

from infrastructure.providers.aws import AWSProvider
from domain.enums import StatusLevel
from domain.models import ServiceStatus


class TestAWSProvider:
    """Test suite for the AWS Status Provider implementation"""

    @pytest.fixture
    def provider(self):
        """Create a fresh AWS provider instance for each test"""
        return AWSProvider()

    @patch('requests.get')
    def test_all_services_operational(self, mock_get, provider):
        """Test when all AWS services are operational"""
        # Mock responses for both endpoints
        mock_events_response = Mock()
        mock_events_response.json.return_value = []
        
        mock_announcement_response = Mock()
        mock_announcement_response.json.return_value = {"description": None}
        
        # Configure the mock to return different responses for different URLs
        mock_get.side_effect = lambda url, **kwargs: {
            "https://health.aws.amazon.com/public/currentevents": mock_events_response,
            "https://health.aws.amazon.com/public/announcement": mock_announcement_response
        }.get(url)
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result
        assert status.provider == "AWS"
        assert status.category == "cloud"
        assert status.status == StatusLevel.OPERATIONAL
        assert "operating normally" in status.message
        
        # Verify both endpoints were called
        assert mock_get.call_count == 2

    @patch('requests.get')
    def test_service_degradation(self, mock_get, provider):
        """Test when AWS reports service degradation"""
        # Create a sample event response with a service degradation
        events_data = {
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
        
        # Mock the events response
        mock_events_response = Mock()
        mock_events_response.json.return_value = events_data
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = mock_events_response
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result
        assert status.provider == "AWS"
        assert status.status == StatusLevel.DEGRADED
        assert "Amazon EC2" in status.message
        assert "increased API error rates" in status.message
        
        # Verify only the events endpoint was called
        assert mock_get.call_count == 1

    @patch('requests.get')
    def test_service_outage(self, mock_get, provider):
        """Test when AWS reports a service outage"""
        # Create a sample event response with a service outage
        events_data = {
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
        
        # Mock the events response
        mock_events_response = Mock()
        mock_events_response.json.return_value = events_data
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = mock_events_response
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result
        assert status.provider == "AWS"
        assert status.status == StatusLevel.OUTAGE
        assert "Amazon S3" in status.message
        assert "outage" in status.message.lower()
        
        # Verify only the events endpoint was called
        assert mock_get.call_count == 1

    @patch('requests.get')
    def test_announcement_only(self, mock_get, provider):
        """Test when AWS has an announcement but no current events"""
        # Mock responses for both endpoints
        mock_events_response = Mock()
        mock_events_response.json.return_value = []
        
        mock_announcement_response = Mock()
        mock_announcement_response.json.return_value = {
            "description": "We will be performing scheduled maintenance on EC2 instances tonight."
        }
        
        # Configure the mock to return different responses for different URLs
        mock_get.side_effect = lambda url, **kwargs: {
            "https://health.aws.amazon.com/public/currentevents": mock_events_response,
            "https://health.aws.amazon.com/public/announcement": mock_announcement_response
        }.get(url)
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result
        assert status.provider == "AWS"
        assert status.status == StatusLevel.DEGRADED
        assert "scheduled maintenance" in status.message
        
        # Verify both endpoints were called
        assert mock_get.call_count == 2

    @patch('requests.get')
    def test_connection_error(self, mock_get, provider):
        """Test graceful degradation when connection fails"""
        # Make requests.get raise an exception
        mock_get.side_effect = requests.RequestException("Connection timeout")
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result shows unknown status with error message
        assert status.provider == "AWS"
        assert status.status == StatusLevel.UNKNOWN
        assert "Unable to fetch" in status.message
        assert "Connection timeout" in status.message

    @patch('requests.get')
    def test_json_parsing_error(self, mock_get, provider):
        """Test handling of invalid JSON response"""
        # Make the JSON parsing fail
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response
        
        # Get the status
        status = provider.get_status()
        
        # Verify the result shows unknown status with parsing error
        assert status.provider == "AWS"
        assert status.status == StatusLevel.UNKNOWN
        assert "parsing AWS status response" in status.message

    @patch('requests.get')
    def test_multiple_affected_services(self, mock_get, provider):
        """Test when multiple AWS services are affected"""
        # Create a sample event response with multiple affected services
        events_data = {
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
        
        # Mock the events response
        mock_events_response = Mock()
        mock_events_response.json.return_value = events_data
        
        # We'll only need the events endpoint for this test
        mock_get.return_value = mock_events_response
        
        # Get the status
        status = provider.get_status()
        
        # Verify all three services are mentioned in the message
        assert status.provider == "AWS"
        assert status.status == StatusLevel.DEGRADED
        assert "Amazon EC2" in status.message
        assert "Amazon RDS" in status.message
        assert "Amazon S3" in status.message