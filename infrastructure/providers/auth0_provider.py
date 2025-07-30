import json
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import requests

from domain import ServiceStatus, StatusLevel, ProviderConfiguration, IncidentReport, ServiceCategory
from application.interfaces.provider import StatusProvider, rate_limit

logger = logging.getLogger(__name__)

class Auth0StatusProvider(StatusProvider):
    """Provider implementation for Auth0 authentication service status."""
    
    def __init__(self) -> None:
        """Initialize the Auth0 status provider.
        
        Args:
            config: Configuration for the Auth0 provider
        """
        config = ProviderConfiguration(
            name="Auth0",
            category=ServiceCategory.AUTHENTICATION,
            status_url="https://status.auth0.com"
        )
        super().__init__(config)
        self._cached_data: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=2)  # Cache TTL of 2 minutes
        
    
    def _fetch_status_data(self) -> Dict[str, Any]:
        """Fetch raw status data from Auth0 with caching.
        
        Returns:
            Dict containing parsed status data from Auth0
            
        Raises:
            ConnectionError: If the Auth0 status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        # Check if we have valid cached data
        if (self._cached_data is not None and 
            self._cache_timestamp is not None and 
            datetime.now(timezone.utc) - self._cache_timestamp < self._cache_ttl):
            logger.debug("Using cached Auth0 status data")
            return self._cached_data
            
        try:
            logger.debug("Fetching fresh Auth0 status data")
            response = requests.get(self.config.status_url, timeout=10.0)
            response.raise_for_status()
            html = response.text
            
            # Extract the JSON data from the __NEXT_DATA__ script tag
            next_data_pattern = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)
            match = next_data_pattern.search(html)
            
            if not match:
                raise ValueError("Could not find __NEXT_DATA__ in HTML")
            
            # Parse the JSON data
            json_data = json.loads(match.group(1))
            
            # The status information is nested in the props.pageProps structure
            status_data = json_data.get('props', {}).get('pageProps', {})
            
            # Update cache
            self._cached_data = status_data
            self._cache_timestamp = datetime.now(timezone.utc)
            
            return status_data
            
        except requests.RequestException as e:
            logger.error(f"Failed to connect to Auth0 status page: {str(e)}")
            raise ConnectionError(f"Failed to fetch Auth0 status: {str(e)}")
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Auth0 status page: {str(e)}")
            raise ValueError(f"Failed to parse Auth0 status data: {str(e)}")
    
    def _fetch_current_status(self) -> ServiceStatus:
        """Fetch and parse the current Auth0 service status.
        
        Returns:
            ServiceStatus: Current status information for Auth0
            
        Raises:
            ConnectionError: If the Auth0 status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        try:
            # Fetch status data (from cache if available)
            status_data = self._fetch_status_data()
            
            # Determine the overall status based on regions
            regions_status = self._extract_regions_status(status_data)
            
            # Determine the worst status across all regions
            overall_status = self._determine_overall_status(regions_status)
            
            # Create a meaningful status message
            status_message = self._create_status_message(regions_status, status_data)
            
            return ServiceStatus(
                provider_name=self.config.name,
                category=self.config.category,
                status_level=overall_status,
                last_checked=datetime.now(timezone.utc),
                message=status_message
            )
            
        except (ConnectionError, ValueError) as e:
            # Re-raise the exception - error handling is done by get_status()
            raise
    
    def _fetch_active_incidents(self) -> list[IncidentReport]:
        """Fetch active incidents from Auth0 status page.
        
        Returns:
            list[IncidentReport]: Currently active incidents
            
        Raises:
            ConnectionError: If the Auth0 incidents page cannot be reached
            ValueError: If the incident page structure is invalid
        """
        # Fetch status data (from cache if available)
        status_data = self._fetch_status_data()
        
        # Extract active incidents
        active_incidents = status_data.get('activeIncidents', [])
        incidents = []
        
        for incident_data in active_incidents:
            region = incident_data.get('region', 'Unknown')
            incident_details = incident_data.get('response', {}).get('incidents', [])
            
            for detail in incident_details:
                if detail.get('status') not in ('resolved', 'operational'):
                    # Convert Auth0 incident to our IncidentReport model
                    incident = IncidentReport(
                        id=detail.get('id', ''),
                        provider_name=self.config.name,
                        title=detail.get('name', 'Unknown Incident'),
                        status_level=self._map_auth0_status_to_level(detail.get('status', 'investigating')),
                        started_at=self._parse_datetime(detail.get('created_at')),
                        resolved_at=None,
                        description=self._extract_latest_update_message(detail)
                    )
                    incidents.append(incident)
        
        return incidents
    
    def _extract_regions_status(self, status_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract status information for each region.
        
        Args:
            status_data: Raw status data from Auth0
            
        Returns:
            Dictionary mapping regions to their status information
        """
        regions_status = {}
        
        # Iterate through the activeIncidents to collect status by region
        for incident in status_data.get('activeIncidents', []):
            region = incident.get('region', 'Unknown')
            uptime = incident.get('response', {}).get('uptime', 'Unknown')
            incidents = incident.get('response', {}).get('incidents', [])
            
            # Filter out operational placeholder incidents
            real_incidents = [
                inc for inc in incidents 
                if not (inc.get('status') == 'operational' and 
                       inc.get('name') == 'All Systems Operational' and
                       inc.get('impact') == 'none')
            ]
            
            regions_status[region] = {
                "uptime": uptime,
                "status": "incident" if real_incidents else "operational"
            }
        
        return regions_status
    
    def _determine_overall_status(self, regions_status: Dict[str, Dict[str, Any]]) -> StatusLevel:
        """Determine the overall status level based on regions status.
        
        Args:
            regions_status: Status information for each region
            
        Returns:
            Overall status level
        """
        # Check if any region has incidents
        has_incidents = any(region.get('status') == 'incident' for region in regions_status.values())
        
        # Check if any region has critical uptime
        critical_uptime = any(
            float(region.get('uptime', '100').replace('%', '').replace('99.999+', '99.999')) < 99.9 
            for region in regions_status.values() 
            if region.get('uptime', '').replace('99.999+', '99.999').replace('%', '').replace('Unknown', '100').replace(' ', '').isdigit() 
               or region.get('uptime', '').replace('99.999+', '99.999').replace('%', '').replace('Unknown', '100').replace(' ', '').replace('.', '', 1).isdigit()
        )
        
        if critical_uptime or has_incidents:
            # More than one region with issues indicates a wider outage
            if sum(1 for region in regions_status.values() if region.get('status') == 'incident') > 1:
                return StatusLevel.OUTAGE
            return StatusLevel.DEGRADED
        
        return StatusLevel.OPERATIONAL
    
    def _create_status_message(self, regions_status: Dict[str, Dict[str, Any]], status_data: Dict[str, Any]) -> str:
        """Create a meaningful status message based on regions status.
        
        Args:
            regions_status: Status information for each region
            status_data: Raw status data from Auth0
            
        Returns:
            Human-readable status message
        """
        # Count regions with incidents
        incident_regions = [region for region, status in regions_status.items() if status.get('status') == 'incident']
        
        if not incident_regions:
            return "All Auth0 services are operational."
        
        # Get the names of the first few incident regions
        region_names = ", ".join(incident_regions[:3])
        if len(incident_regions) > 3:
            region_names += f" and {len(incident_regions) - 3} more regions"
        
        # Find the most recent incident with updates
        recent_incident = None
        recent_update = None
        
        for incident in status_data.get('activeIncidents', []):
            for detail in incident.get('response', {}).get('incidents', []):
                if not recent_incident or self._parse_datetime(detail.get('updated_at')) > self._parse_datetime(recent_incident.get('updated_at')):
                    recent_incident = detail
                    for update in detail.get('incident_updates', []):
                        if not recent_update or self._parse_datetime(update.get('created_at')) > self._parse_datetime(recent_update.get('created_at')):
                            recent_update = update
        
        if recent_incident and recent_update:
            update_body = recent_update.get('body', '')
            if len(update_body) > 100:
                update_body = update_body[:97] + '...'
            
            impact = recent_incident.get('impact', 'unknown')
            return f"{impact.upper()} impact in {region_names}: {update_body}"
        
        # Fallback message if we can't find specific incident details
        return f"Service disruption detected in {region_names}. Check Auth0 status page for details."
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> datetime:
        """Parse an ISO format datetime string to a datetime object.
        
        Args:
            datetime_str: ISO format datetime string
            
        Returns:
            Datetime object (or current time if parsing fails)
        """
        if not datetime_str:
            return datetime.now(timezone.utc)
            
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse datetime: {datetime_str}")
            return datetime.now(timezone.utc)
    
    def _extract_affected_components(self, incident: Dict[str, Any]) -> list[str]:
        """Extract affected components from an incident.
        
        Args:
            incident: Incident data
            
        Returns:
            List of affected component names
        """
        components = []
        
        # Check the latest update for affected components
        for update in incident.get('incident_updates', []):
            affected = update.get('affected_components', [])
            for component in affected:
                name = component.get('name', '')
                if name and name not in components:
                    components.append(name)
        
        return components
    
    def _extract_latest_update_message(self, incident: Dict[str, Any]) -> str:
        """Extract the latest update message from an incident.
        
        Args:
            incident: Incident data
            
        Returns:
            Latest update message
        """
        # Sort updates by creation time (newest first)
        sorted_updates = sorted(
            incident.get('incident_updates', []),
            key=lambda x: self._parse_datetime(x.get('created_at')),
            reverse=True
        )
        
        # Get the message from the most recent update
        if sorted_updates:
            return sorted_updates[0].get('body', 'No update message available')
        
        return "No updates available"
    
    def _map_auth0_status_to_level(self, status: str) -> StatusLevel:
        """Map Auth0 status string to StatusLevel enum."""
        status_map = {
            'investigating': StatusLevel.DEGRADED,
            'identified': StatusLevel.DEGRADED,
            'monitoring': StatusLevel.DEGRADED,
            'resolved': StatusLevel.OPERATIONAL,
            'scheduled': StatusLevel.DEGRADED
        }
        return status_map.get(status.lower(), StatusLevel.UNKNOWN)