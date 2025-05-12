#docker-compose exec web pytest tests/infrastructure/providers/test_integration_providers.py -v -m integration

import os
import json
import pytest
import logging
from datetime import datetime, timezone
from pathlib import Path

from domain import StatusLevel, ServiceCategory
from infrastructure.providers.stripe_provider import StripeProvider
from infrastructure.providers.auth0_provider import Auth0StatusProvider
from infrastructure.providers.okta_provider import OktaStatusProvider
from infrastructure.providers.aws_provider import AWSProvider
from infrastructure.providers.square_provider import SquareProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create directory for saving responses
RESPONSES_DIR = Path("test_responses")
RESPONSES_DIR.mkdir(exist_ok=True)

def save_response(provider_name, endpoint, content, content_type="html"):
    """Save API response to file for manual inspection."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{provider_name}_{endpoint}_{timestamp}.{content_type}"
    filepath = RESPONSES_DIR / filename
    
    # Save the content
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"Saved response to {filepath}")
    return filepath

@pytest.mark.integration
@pytest.mark.live
class TestProviderIntegration:
    """Integration tests for provider implementations with actual status pages."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        # Create timestamp directory for this test run
        self.test_run_dir = RESPONSES_DIR / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.test_run_dir.mkdir(exist_ok=True)
    
    def save_provider_response(self, provider_name, content_type, content):
        """Save provider response to file."""
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        filename = f"{provider_name}_{timestamp}.{content_type}"
        filepath = self.test_run_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            if content_type == "json":
                json.dump(content, f, indent=2)
            else:
                f.write(content)
        
        logger.info(f"Saved {provider_name} response to {filepath}")
        return filepath
    
    def save_status_result(self, provider_name, status):
        """Save parsed status result to file."""
        result = {
            "provider_name": status.provider_name,
            "category": status.category.value,
            "status_level": status.status_level.value,
            "message": status.message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        filepath = self.test_run_dir / f"{provider_name}_status_result.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Saved {provider_name} status result to {filepath}")
    
    def save_incident_results(self, provider_name, incidents):
        """Save parsed incident results to file."""
        results = []
        for incident in incidents:
            result = {
                "id": incident.id,
                "title": incident.title,
                "status_level": incident.status_level.value,
                "started_at": incident.started_at.isoformat() if incident.started_at else None,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "description": incident.description
            }
            results.append(result)
        
        filepath = self.test_run_dir / f"{provider_name}_incidents_result.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Saved {provider_name} incident results to {filepath}")
    
    @pytest.mark.timeout(30)  # Set timeout for each test
    def test_stripe_provider_integration(self):
        """Test Stripe provider with real status API."""
        provider = StripeProvider()
        
        try:
            # Test status endpoint
            status_data = provider._make_api_request(provider.STATUS_ENDPOINT)
            self.save_provider_response("stripe_status", "json", status_data)
            
            # Test incidents endpoint
            incidents_data = provider._make_api_request(provider.INCIDENTS_ENDPOINT)
            self.save_provider_response("stripe_incidents", "json", incidents_data)
            
            # Test components endpoint
            components_data = provider._make_api_request(provider.COMPONENTS_ENDPOINT)
            self.save_provider_response("stripe_components", "json", components_data)
            
            # Test status parsing
            status = provider.get_status()
            assert status.provider_name == "Stripe"
            assert isinstance(status.status_level, StatusLevel)
            assert isinstance(status.category, ServiceCategory)
            assert status.message is not None
            self.save_status_result("stripe", status)
            
            # Test incident parsing
            incidents = provider.get_incidents()
            self.save_incident_results("stripe", incidents)
            
            logger.info(f"Stripe current status: {status.status_level.value}")
            logger.info(f"Active incidents: {len(incidents)}")
            
        except Exception as e:
            logger.error(f"Error testing Stripe provider: {e}")
            pytest.fail(f"Stripe provider integration test failed: {e}")
    
    @pytest.mark.timeout(30)
    def test_auth0_provider_integration(self):
        """Test Auth0 provider with real status page."""
        provider = Auth0StatusProvider()
        
        try:
            # Capture raw HTML response for Auth0
            import requests
            response = requests.get(provider.config.status_url, timeout=15)
            html_content = response.text
            self.save_provider_response("auth0_raw", "html", html_content)
            
            # Test status parsing
            status = provider.get_status()
            assert status.provider_name == "Auth0"
            assert isinstance(status.status_level, StatusLevel)
            assert isinstance(status.category, ServiceCategory)
            assert status.message is not None
            self.save_status_result("auth0", status)
            
            # Test incident parsing
            incidents = provider.get_incidents()
            self.save_incident_results("auth0", incidents)
            
            logger.info(f"Auth0 current status: {status.status_level.value}")
            logger.info(f"Active incidents: {len(incidents)}")
            
        except Exception as e:
            logger.error(f"Error testing Auth0 provider: {e}")
            pytest.fail(f"Auth0 provider integration test failed: {e}")
    
    @pytest.mark.timeout(30)
    def test_okta_provider_integration(self):
        """Test Okta provider with real status page."""
        provider = OktaStatusProvider()
        
        try:
            # Capture raw HTML response for Okta
            import requests
            response = requests.get(provider.config.status_url, headers=provider.headers, timeout=15)
            html_content = response.text
            self.save_provider_response("okta_raw", "html", html_content)
            
            # Test status parsing
            status = provider.get_status()
            assert status.provider_name == "Okta"
            assert isinstance(status.status_level, StatusLevel)
            assert isinstance(status.category, ServiceCategory)
            assert status.message is not None
            self.save_status_result("okta", status)
            
            # Test incident parsing
            incidents = provider.get_incidents()
            self.save_incident_results("okta", incidents)
            
            logger.info(f"Okta current status: {status.status_level.value}")
            logger.info(f"Active incidents: {len(incidents)}")
            
        except Exception as e:
            logger.error(f"Error testing Okta provider: {e}")
            pytest.fail(f"Okta provider integration test failed: {e}")
    
    @pytest.mark.timeout(30)
    def test_aws_provider_integration(self):
        """Test AWS provider with real status page."""
        provider = AWSProvider()
        
        try:
            # Test current events endpoint
            import requests
            events_response = requests.get(provider._current_events_url, timeout=10)
            events_content = events_response.content
            # Handle UTF-16 encoding with BOM
            events_text = events_content.decode('utf-16')
            events_data = json.loads(events_text)
            self.save_provider_response("aws_events", "json", events_data)
            
            # Test announcement endpoint
            announcement_response = requests.get(provider._announcement_url, timeout=10)
            announcement_content = announcement_response.content
            # Handle UTF-16 encoding with BOM
            announcement_text = announcement_content.decode('utf-16')
            announcement_data = json.loads(announcement_text)
            self.save_provider_response("aws_announcement", "json", announcement_data)
            
            # Test status parsing
            status = provider.get_status()
            assert status.provider_name == "AWS"
            assert isinstance(status.status_level, StatusLevel)
            assert isinstance(status.category, ServiceCategory)
            assert status.message is not None
            self.save_status_result("aws", status)
            
            # Test incident parsing
            incidents = provider.get_incidents()
            self.save_incident_results("aws", incidents)
            
            logger.info(f"AWS current status: {status.status_level.value}")
            logger.info(f"Active incidents: {len(incidents)}")
            
        except Exception as e:
            logger.error(f"Error testing AWS provider: {e}")
            pytest.fail(f"AWS provider integration test failed: {e}")
    
    @pytest.mark.timeout(30)
    def test_square_provider_integration(self):
        """Test Square provider with real status page."""
        provider = SquareProvider()
        
        try:
            # Capture raw HTML response for Square
            import requests
            response = requests.get(provider.config.status_url, timeout=10)
            html_content = response.text
            self.save_provider_response("square_raw", "html", html_content)
            
            # Test status parsing
            status = provider.get_status()
            assert status.provider_name == "Square"
            assert isinstance(status.status_level, StatusLevel)
            assert isinstance(status.category, ServiceCategory)
            assert status.message is not None
            self.save_status_result("square", status)
            
            # Test incident parsing
            incidents = provider.get_incidents()
            self.save_incident_results("square", incidents)
            
            # Test detailed status
            detailed_statuses = provider.get_detailed_status()
            detailed_results = {
                region: {
                    "status_level": status.status_level.value,
                    "message": status.message
                }
                for region, status in detailed_statuses.items()
            }
            self.save_provider_response("square_detailed", "json", detailed_results)
            
            logger.info(f"Square current status: {status.status_level.value}")
            logger.info(f"Active incidents: {len(incidents)}")
            logger.info(f"Regions: {len(detailed_statuses)}")
            
        except Exception as e:
            logger.error(f"Error testing Square provider: {e}")
            pytest.fail(f"Square provider integration test failed: {e}")