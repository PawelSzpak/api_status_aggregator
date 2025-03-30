from datetime import datetime, timezone, timedelta
import json
import re
import logging
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

from domain import ServiceStatus, StatusLevel, ProviderConfiguration, IncidentReport, ServiceCategory
from application.interfaces.provider import StatusProvider, rate_limit

logger = logging.getLogger(__name__)

class OktaStatusProvider(StatusProvider):
    """Provider implementation for Okta authentication service status."""
    
    def __init__(self) -> None:
        """Initialize the Okta status provider with configuration."""
        config = ProviderConfiguration(
            name="Okta",
            category=ServiceCategory.AUTHENTICATION,
            status_url="https://status.okta.com"
        )
        super().__init__(config)
        
        # Set up request headers to appear as a legitimate browser
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        
        # Cache for status data
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = timedelta(minutes=2)  # Cache TTL of 2 minutes
    
    @rate_limit(calls=4, period=60)  # Max 4 requests per minute
    def _fetch_status_data(self) -> Dict[str, Any]:
        """
        Fetch raw status data from Okta with caching.
        
        Returns:
            Dict containing parsed status data from Okta
            
        Raises:
            ConnectionError: If the Okta status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        # Check if cache is valid
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_time and now - self._cache_time < self._cache_ttl:
            logger.debug("Using cached Okta status data")
            return self._cache
        
        try:
            logger.debug("Fetching fresh Okta status data")
            response = requests.get(self.config.status_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the JSON data in the span element
            json_span = soup.find('span', {'id': 'j_id0:j_id8:StringJSON'})
            if not json_span:
                raise ValueError("Could not find status JSON data in Okta status page")
            
            # Parse the JSON data
            incidents_data = json.loads(json_span.text)
            
            # Find the uptime data
            uptime_span = soup.find('span', {'id': 'j_id0:j_id8:UptimeJSON'})
            if uptime_span:
                uptime_data = json.loads(uptime_span.text)
            else:
                uptime_data = []
            
            # Combine data
            data = {
                'incidents': incidents_data,
                'uptime': uptime_data
            }
            
            # Update cache
            self._cache = data
            self._cache_time = now
            
            return data
            
        except requests.RequestException as e:
            logger.error(f"Failed to connect to Okta status page: {str(e)}")
            raise ConnectionError(f"Failed to fetch Okta status: {str(e)}")
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Okta status page: {str(e)}")
            raise ValueError(f"Failed to parse Okta status data: {str(e)}")
    
    def _fetch_current_status(self) -> ServiceStatus:
        """
        Fetch and parse the current Okta service status.
        
        Returns:
            ServiceStatus: Current status information for Okta
            
        Raises:
            ConnectionError: If the Okta status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        # Fetch status data (from cache if available)
        status_data = self._fetch_status_data()
        
        # Get active incidents (unresolved)
        active_incidents = [
            incident for incident in status_data.get('incidents', [])
            if incident.get('Status__c') != 'Resolved'
        ]
        
        # Determine the status level based on active incidents
        status_level = self._determine_status_level(active_incidents)
        
        # Create a meaningful status message
        status_message = self._create_status_message(active_incidents)
        
        # Most recent uptime data
        current_uptime = None
        uptime_data = status_data.get('uptime', [])
        if uptime_data:
            # Sort by year to get the most recent
            sorted_uptime = sorted(uptime_data, key=lambda x: x.get('year', 0), reverse=True)
            if sorted_uptime:
                current_uptime = sorted_uptime[0].get('uptime')
        
        # Add uptime information to the message if available
        if current_uptime is not None:
            status_message = f"{status_message} Current uptime: {current_uptime}%"
        
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=status_level,
            last_checked=datetime.now(timezone.utc),
            message=status_message
        )
    
    def _fetch_active_incidents(self) -> List[IncidentReport]:
        """
        Fetch active incidents from Okta status page.
        
        Returns:
            List[IncidentReport]: Currently active incidents
            
        Raises:
            ConnectionError: If the Okta incidents page cannot be reached
            ValueError: If the incident page structure is invalid
        """
        # Fetch status data (from cache if available)
        status_data = self._fetch_status_data()
        
        # Get active (and recently resolved) incidents for better coverage
        incidents = []
        for incident_data in status_data.get('incidents', []):
            # Skip incidents older than 7 days
            if incident_data.get('Status__c') == 'Resolved':
                # If there's an end date, check if it's within 7 days
                if not incident_data.get('End_Date__c'):
                    continue
                
                # Parse the date and check if it's recent
                try:
                    end_date_str = incident_data.get('End_Date__c', '')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    days_ago = (datetime.now() - end_date).days
                    if days_ago > 7:  # Skip if more than 7 days old
                        continue
                except (ValueError, TypeError):
                    continue
            
            # Map Okta incident status to our status level
            status_level = self._map_incident_status(incident_data.get('Status__c', ''),
                                                   incident_data.get('Category__c', ''))
            
            # Parse start/end dates
            started_at = self._parse_datetime(incident_data.get('Start_Time__c'))
            resolved_at = self._parse_datetime(incident_data.get('End_Time__c')) if incident_data.get('Status__c') == 'Resolved' else None
            
            if started_at is None:
                started_at = datetime.now(timezone.utc)

            # Extract updates if available
            updates = []
            incident_id = incident_data.get('Id')
            if incident_id:
                for update in status_data.get('updates', []):
                    if update.get('IncidentId__c') == incident_id:
                        updates.append(update.get('UpdateLog__c', ''))
            
            # Create incident report
            incident = IncidentReport(
                id=incident_data.get('Id', ''),
                provider_name=self.config.name,
                title=incident_data.get('Incident_Title__c', 'Unnamed Incident'),
                status_level=status_level,
                started_at=started_at,
                resolved_at=resolved_at,
                description=incident_data.get('Log__c', '')
            )
            
            incidents.append(incident)
        
        return incidents
    
    def _determine_status_level(self, active_incidents: List[Dict[str, Any]]) -> StatusLevel:
        """
        Determine the overall status level based on active incidents.
        
        Args:
            active_incidents: List of active incident data
            
        Returns:
            Overall status level
        """
        if not active_incidents:
            return StatusLevel.OPERATIONAL
        
        # Check for major outages
        for incident in active_incidents:
            category = incident.get('Category__c', '')
            if category == 'Major Service Disruption':
                return StatusLevel.OUTAGE
        
        # Check for service disruptions
        for incident in active_incidents:
            category = incident.get('Category__c', '')
            if category == 'Service Disruption':
                return StatusLevel.OUTAGE
            
        # Check for degradations
        for incident in active_incidents:
            category = incident.get('Category__c', '')
            if category in ['Service Degradation', 'Performance Issue']:
                return StatusLevel.DEGRADED
        
        # Default to degraded if there are any incidents without recognized categories
        return StatusLevel.DEGRADED
    
    def _create_status_message(self, active_incidents: List[Dict[str, Any]]) -> str:
        """
        Create a meaningful status message based on active incidents.
        
        Args:
            active_incidents: List of active incident data
            
        Returns:
            Human-readable status message
        """
        if not active_incidents:
            return "All Okta services are operational."
        
        # Count incidents by category
        incident_counts = {}
        for incident in active_incidents:
            category = incident.get('Category__c', 'Unknown')
            incident_counts[category] = incident_counts.get(category, 0) + 1
        
        # Create summary message
        summary_parts = []
        for category, count in incident_counts.items():
            summary_parts.append(f"{count} {category}")
        
        # Add the most recent incident title
        most_recent = sorted(
            active_incidents, 
            key=lambda x: self._parse_datetime(x.get('Start_Time__c')) or datetime.min,
            reverse=True
        )[0]
        
        title = most_recent.get('Incident_Title__c', '')
        if title:
            summary = ", ".join(summary_parts)
            return f"Okta is experiencing issues: {summary}. Latest incident: {title}"
        else:
            summary = " and ".join(summary_parts)
            return f"Okta is experiencing issues: {summary}."
    
    def _map_incident_status(self, status_str: str, category_str: str) -> StatusLevel:
        """
        Map Okta incident status to our StatusLevel enum.
        
        Args:
            status_str: Status string from Okta
            category_str: Category string from Okta
            
        Returns:
            Mapped StatusLevel
        """
        if status_str == 'Resolved':
            return StatusLevel.OPERATIONAL
        
        if category_str == 'Major Service Disruption':
            return StatusLevel.OUTAGE
        
        if category_str == 'Service Disruption':
            return StatusLevel.OUTAGE
        
        if category_str in ['Service Degradation', 'Performance Issue']:
            return StatusLevel.DEGRADED
        
        # Default for any other active incident
        return StatusLevel.DEGRADED
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """
        Parse an ISO format datetime string to a datetime object.
        
        Args:
            datetime_str: ISO format datetime string
            
        Returns:
            Datetime object or None if parsing fails
        """
        if not datetime_str:
            return None
            
        try:
            # Format: 2023-11-15T12:14:00.000+0000
            # Need to handle both Z and +0000 timezone formats
            if datetime_str.endswith('Z'):
                dt_string = datetime_str[:-1] + '+00:00'
            elif '+' in datetime_str:
                # Split at +, keep everything before, then append proper timezone
                dt_parts = datetime_str.split('+')
                dt_string = dt_parts[0] + '+' + dt_parts[1].replace('0000', '00:00')
            else:
                dt_string = datetime_str
                
            return datetime.fromisoformat(dt_string)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse datetime '{datetime_str}': {str(e)}")
            return None