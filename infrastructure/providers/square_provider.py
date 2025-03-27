from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
import logging

from domain import ServiceStatus, StatusLevel, ProviderConfiguration, IncidentReport
from application.interfaces.provider import StatusProvider, rate_limit

logger = logging.getLogger(__name__)

class SquareProvider(StatusProvider):
    """Status provider implementation for Square payment services."""
    
    def __init__(self):
        super().__init__(
            name="Square",
            category="payment",
            status_url="https://www.issquareup.com/?forceParent=true"  # Parent page with all regions
        )
        self._last_known_status = None
    
    @rate_limit(calls=1, period=60)  # One request per minute
    def get_status(self) -> ServiceStatus:
        """Fetch and return global status by examining all regional statuses."""
        try:
            response = requests.get(self.status_url, timeout=10)
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
            
            status = ServiceStatus(
                provider=self.name,
                category=self.category,
                status=status_level,
                last_updated=datetime.now(timezone.utc),
                message=message
            )
            
            # Cache for error handling
            self._last_known_status = status
            return status
            
        except Exception as e:
            logger.error(f"Error fetching Square global status: {e}", exc_info=True)
            if self._last_known_status:
                # Return last known with updated message
                return ServiceStatus(
                    provider=self._last_known_status.provider,
                    category=self._last_known_status.category,
                    status=self._last_known_status.status,
                    last_updated=datetime.now(timezone.utc),
                    message=f"{self._last_known_status.message} (from cached status)"
                )
            
            # Default fallback if we have no cached status
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=StatusLevel.OPERATIONAL,
                last_updated=datetime.now(timezone.utc),
                message="Unable to determine current status, assuming operational"
            )
    
    def get_detailed_status(self) -> Dict[str, ServiceStatus]:
        """Optional method to retrieve status for each individual region."""
        region_statuses = {}
        try:
            response = requests.get(self.status_url, timeout=10)
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
                    provider=f"Square {region_name}",
                    category=self.category,
                    status=status_level,
                    last_updated=datetime.now(timezone.utc),
                    message=f"Square {region_name}: {status_level.value}"
                )
            
            return region_statuses
            
        except Exception as e:
            logger.error(f"Error fetching detailed Square status: {e}")
            return {}