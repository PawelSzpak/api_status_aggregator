from datetime import datetime, timezone
import requests
from typing import List, Optional, Dict, Any
import logging

from application.interfaces import StatusProvider, rate_limit
from domain.enums import StatusLevel, ServiceCategory, ServiceStatus
from domain.models import ProviderConfiguration, IncidentReport

logger = logging.getLogger(__name__)

class StripeProvider(StatusProvider):
    """Stripe status provider implementation using their API endpoints."""
    
    # API endpoint constants
    BASE_URL = "https://www.stripestatus.com/api/v2"
    STATUS_ENDPOINT = "/status.json"
    COMPONENTS_ENDPOINT = "/components.json"
    INCIDENTS_ENDPOINT = "/incidents.json"
    
    # Status mapping from Stripe's terminology to our StatusLevel enum
    STATUS_MAPPING = {
        "none": StatusLevel.OPERATIONAL,
        "minor": StatusLevel.DEGRADED,
        "major": StatusLevel.DEGRADED,
        "critical": StatusLevel.OUTAGE,
        "maintenance": StatusLevel.DEGRADED,
        
        # Component-specific statuses
        "operational": StatusLevel.OPERATIONAL,
        "degraded_performance": StatusLevel.DEGRADED,
        "partial_outage": StatusLevel.DEGRADED,
        "major_outage": StatusLevel.OUTAGE
    }
    
    def __init__(self) -> None:
        """Initialize the Stripe provider with configuration."""
        config = ProviderConfiguration(
            name="Stripe",
            category=ServiceCategory.PAYMENT,
            status_url="https://www.stripestatus.com"
        )
        super().__init__(config)
        
        # Set up request headers to appear as a legitimate browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json"
        }
        
    @rate_limit(calls=6, period=60)
    def _make_api_request(self, endpoint: str) -> Dict[str, Any]:
        """
        Make a rate-limited API request to the Stripe status page.
        
        Args:
            endpoint: The API endpoint to request
            
        Returns:
            Dict: The JSON response data
            
        Raises:
            ConnectionError: If the request fails
            ValueError: If the response is not valid JSON
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch Stripe status from {url}: {str(e)}")
            raise ConnectionError(f"Failed to connect to Stripe status API: {str(e)}")
        except ValueError as e:
            logger.error(f"Failed to parse Stripe status response: {str(e)}")
            raise ValueError(f"Invalid response from Stripe status API: {str(e)}")
    
    def fetch_current_status(self) -> ServiceStatus:
        """
        Fetch and parse the current Stripe service status.
        
        Returns:
            ServiceStatus: Current status information
            
        Raises:
            ConnectionError: If the status API cannot be reached
            ValueError: If the response cannot be parsed
        """
        # Fetch the overall status
        status_data = self._make_api_request(self.STATUS_ENDPOINT)
        
        # Extract the status indicator and description
        indicator = status_data.get("status", {}).get("indicator", "unknown")
        description = status_data.get("status", {}).get("description", "Status information unavailable")
        
        # Map the indicator to our status levels
        status_level = self.STATUS_MAPPING.get(indicator, StatusLevel.UNKNOWN)
        
        # Check if there are any active incidents that might affect the status
        try:
            incidents = self._make_api_request(self.INCIDENTS_ENDPOINT)
            active_incidents = [i for i in incidents.get("incidents", []) 
                               if i.get("status") != "resolved"]
            
            # If there are active incidents, update the status level based on impact
            if active_incidents:
                incident_impacts = [i.get("impact", "none") for i in active_incidents]
                
                # Update status level based on the most severe incident
                if "critical" in incident_impacts:
                    status_level = StatusLevel.OUTAGE
                elif "major" in incident_impacts and status_level != StatusLevel.OUTAGE:
                    status_level = StatusLevel.DEGRADED
                elif "minor" in incident_impacts and status_level == StatusLevel.OPERATIONAL:
                    status_level = StatusLevel.DEGRADED
                
                # Append incident information to the description
                incident_titles = [i.get("name", "Unnamed incident") for i in active_incidents]
                description = f"{description} - Active incidents: {', '.join(incident_titles)}"
        except (ConnectionError, ValueError) as e:
            # If we can't fetch incidents, log the error but continue with the overall status
            logger.warning(f"Failed to fetch Stripe incidents: {str(e)}")
        
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=status_level,
            last_checked=datetime.now(timezone.utc),
            message=description
        )
    
    def fetch_active_incidents(self) -> List[IncidentReport]:
        """
        Fetch active incidents from Stripe's status API.
        
        Returns:
            List[IncidentReport]: Active incidents
            
        Raises:
            ConnectionError: If the incidents API cannot be reached
            ValueError: If the response cannot be parsed
        """
        incidents_data = self._make_api_request(self.INCIDENTS_ENDPOINT)
        incidents = []
        
        for incident in incidents_data.get("incidents", []):
            # Skip resolved incidents
            if incident.get("status") == "resolved":
                continue
                
            # Parse the incident data
            incident_id = incident.get("id", "unknown")
            title = incident.get("name", "Unnamed incident")
            impact = incident.get("impact", "none")
            
            # Parse timestamps
            started_at_str = incident.get("started_at")
            started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00")) if started_at_str else datetime.now(timezone.utc)
            
            resolved_at_str = incident.get("resolved_at")
            resolved_at = datetime.fromisoformat(resolved_at_str.replace("Z", "+00:00")) if resolved_at_str else None
            
            # Extract updates
            updates = []
            for update in incident.get("incident_updates", []):
                body = update.get("body", "")
                if body:
                    updates.append(body)
            
            # Map the impact to our status levels
            status_level = self.STATUS_MAPPING.get(impact, StatusLevel.UNKNOWN)
            
            # Create the incident report
            incident_report = IncidentReport(
                id=incident_id,
                provider_name=self.config.name,
                status_level=status_level,
                started_at=started_at,
                resolved_at=resolved_at,
                title=title,
                description=updates[0] if updates else None,
                updates=updates
            )
            
            incidents.append(incident_report)
        
        return incidents
    
    def get_component_statuses(self) -> List[ServiceStatus]:
        """
        Fetch the status of individual Stripe components.
        
        Returns:
            List[ServiceStatus]: Status of each component
            
        Note:
            This is an additional method not required by the base interface,
            but useful for detailed monitoring of Stripe's components.
        """
        components_data = self._make_api_request(self.COMPONENTS_ENDPOINT)
        component_statuses = []
        
        for component in components_data.get("components", []):
            name = component.get("name", "Unknown component")
            status = component.get("status", "unknown")
            
            # Map the status to our status levels
            status_level = self.STATUS_MAPPING.get(status, StatusLevel.UNKNOWN)
            
            component_status = ServiceStatus(
                provider_name=f"{self.config.name} - {name}",
                category=self.config.category,
                status_level=status_level,
                last_checked=datetime.now(timezone.utc),
                message=f"Component: {name}, Status: {status}"
            )
            
            component_statuses.append(component_status)
        
        return component_statuses