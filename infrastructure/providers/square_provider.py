from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
import logging

from domain import ServiceStatus, StatusLevel, ProviderConfiguration, IncidentReport, ServiceCategory
from application.interfaces.provider import StatusProvider, rate_limit

logger = logging.getLogger(__name__)

class SquareProvider(StatusProvider):
    """Status provider implementation for Square payment services."""
    
    def __init__(self) -> None:
        """Initialize the Square status provider with configuration."""
        config = ProviderConfiguration(
            name="Square",
            category=ServiceCategory.PAYMENT,
            status_url="https://www.issquareup.com/?forceParent=true"  # Parent page with all regions
        )
        super().__init__(config)
    
    def _fetch_current_status(self) -> ServiceStatus:
        """Fetch and return global status by examining all regional statuses.
        
        Returns:
            ServiceStatus: Current status information
            
        Raises:
            ConnectionError: If the Square status page cannot be reached
            ValueError: If the page structure is invalid
        """
        response = requests.get(self.config.status_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all region entries in the parent page
        region_elements = soup.find_all("a", {"class": lambda c: c and "first:rounded-t-md" in c})
        
        # Track regions with issues
        regions_with_issues = []
        
        for region_element in region_elements:
            # Each region entry has an SVG icon indicating status
            status_icon = region_element.find("svg", {"class": lambda c: c and "text-icon-" in c})
            region_name = region_element.get_text(strip=True)
            
            # If not operational, add to issue list
            if status_icon and "text-icon-operational" not in status_icon.get("class", []):
                regions_with_issues.append(region_name)
        
        # Determine overall status based on affected regions
        if not regions_with_issues:
            status_level = StatusLevel.OPERATIONAL
            message = "All Square services are operational across all regions"
        else:
            status_level = StatusLevel.DEGRADED
            message = f"Square is experiencing issues in the following regions: {', '.join(regions_with_issues)}"
        
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=status_level,
            last_checked=datetime.now(timezone.utc),
            message=message
        )
    
    def _fetch_active_incidents(self) -> List[IncidentReport]:
        """Fetch active incidents from Square status page.
        
        Returns:
            List[IncidentReport]: Currently active incidents
            
        Raises:
            ConnectionError: If the Square status page cannot be reached
            ValueError: If the page structure is invalid
        """
        incidents = []
        
        response = requests.get(self.config.status_url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all region entries
        region_elements = soup.find_all("a", {"class": lambda c: c and "first:rounded-t-md" in c})
        
        for region_element in region_elements:
            region_name = region_element.get_text(strip=True)
            status_icon = region_element.find("svg", {"class": lambda c: c and "text-icon-" in c})
            
            # Only process regions with issues
            if status_icon and "text-icon-operational" not in status_icon.get("class", []):
                # Extract the region URL to fetch detailed incident information
                region_url = f"https://www.issquareup.com{region_element.get('href', '')}"
                
                try:
                    # Fetch the region-specific page for incident details
                    region_response = requests.get(region_url, timeout=10)
                    region_soup = BeautifulSoup(region_response.text, 'html.parser')
                    
                    # Find incident entries (this would need to be adapted to the actual page structure)
                    incident_elements = region_soup.find_all("div", {"class": "incident-entry"})
                    
                    for incident_element in incident_elements:
                        # Extract incident details (adapt to actual structure)
                        title_element = incident_element.find("h3", {"class": "incident-title"})
                        title = title_element.get_text(strip=True) if title_element else f"Issue in {region_name}"
                        
                        status_element = incident_element.find("span", {"class": "incident-status"})
                        status = status_element.get_text(strip=True) if status_element else "investigating"
                        
                        message_element = incident_element.find("div", {"class": "incident-message"})
                        message = message_element.get_text(strip=True) if message_element else f"Service disruption in {region_name}"
                        
                        # Map status to status level
                        status_level = StatusLevel.DEGRADED
                        if status.lower() == "resolved":
                            status_level = StatusLevel.OPERATIONAL
                        elif "outage" in status.lower():
                            status_level = StatusLevel.OUTAGE

                        # Create incident report
                        incident = IncidentReport(
                            id=f"square-{region_name}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                            provider_name=self.config.name,
                            title=title,
                            status_level=status_level,
                            started_at=datetime.now(timezone.utc),  # Approximate if not available
                            resolved_at=None,
                            description=message
                        )
                        
                        incidents.append(incident)
                        
                except (requests.RequestException, ValueError) as e:
                    # If we can't get details, create a basic incident report
                    logger.warning(f"Error fetching Square incident details for {region_name}: {e}")
                    incident = IncidentReport(
                        id=f"square-{region_name}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                        provider=self.config.name,
                        title=f"Service disruption in {region_name}",
                        status="investigating",
                        impact="major",
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                        region=region_name,
                        affected_components=[region_name],
                        message=f"Ongoing service disruption in {region_name}. Check Square status page for details."
                    )
                    incidents.append(incident)
        
        return incidents
    
    def get_detailed_status(self) -> Dict[str, ServiceStatus]:
        """Optional method to retrieve status for each individual region.
        
        Returns:
            Dict[str, ServiceStatus]: Status for each region
        """
        region_statuses = {}
        try:
            response = requests.get(self.config.status_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            region_elements = soup.find_all("a", {"class": lambda c: c and "first:rounded-t-md" in c})
            
            for region_element in region_elements:
                status_icon = region_element.find("svg", {"class": lambda c: c and "text-icon-" in c})
                region_name = region_element.get_text(strip=True)
                region_url = f"https://www.issquareup.com{region_element.get('href', '')}"
                
                status_level = StatusLevel.OPERATIONAL
                if status_icon and "text-icon-operational" not in status_icon.get("class", []):
                    # Determine specific level based on class
                    if "text-icon-degraded" in status_icon.get("class", []):
                        status_level = StatusLevel.DEGRADED
                    else:
                        status_level = StatusLevel.OUTAGE
                
                region_statuses[region_name] = ServiceStatus(
                    provider_name=f"Square {region_name}",
                    category=self.config.category,
                    status_level=status_level,
                    last_checked=datetime.now(timezone.utc),
                    message=f"Square {region_name}: {status_level.value}"
                )
            
            return region_statuses
            
        except Exception as e:
            logger.error(f"Error fetching detailed Square status: {e}")
            return {}