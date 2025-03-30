from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

from application.interfaces.provider import StatusProvider, rate_limit
from domain import ServiceStatus, StatusLevel, IncidentReport, ProviderConfiguration, ServiceCategory

class AWSProvider(StatusProvider):
    """AWS Status Provider implementation using their health API endpoints"""
    
    def __init__(self) -> None:
        """Initialize the AWS status provider with configuration."""
        config = ProviderConfiguration(
            name="AWS",
            category=ServiceCategory.CLOUD,
            status_url="https://health.aws.amazon.com/health/status"
        )
        super().__init__(config)
        self._current_events_url = "https://health.aws.amazon.com/public/currentevents"
        self._announcement_url = "https://health.aws.amazon.com/public/announcement"
        
    def _fetch_current_status(self) -> ServiceStatus:
        """Fetch AWS current service status
        
        Returns:
            ServiceStatus: Current status information
            
        Raises:
            ConnectionError: If the AWS API cannot be reached
            ValueError: If the response cannot be parsed
        """
        # Check current events first (active incidents)
        events_response = requests.get(self._current_events_url, timeout=10)
        events_response.raise_for_status()
        
        events = events_response.json()
        
        # If we have active events, parse them to determine status
        if events and len(events) > 0:
            return self._parse_events(events)
            
        # If no active events, check if there's an announcement
        announcement_response = requests.get(self._announcement_url, timeout=10)
        announcement_response.raise_for_status()
        
        announcement = announcement_response.json()
        if announcement and announcement.get("description"):
            return self._parse_announcement(announcement)
        
        # No events or announcements means all systems operational
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All AWS services operating normally"
        )
        
    def _fetch_active_incidents(self) -> list[IncidentReport]:
        """Fetch any active incidents from AWS.
        
        Returns:
            list[IncidentReport]: Currently active incidents
            
        Raises:
            ConnectionError: If the incidents API cannot be reached
            ValueError: If the response cannot be parsed
        """
        incidents = []
        
        # Fetch current events
        events_response = requests.get(self._current_events_url, timeout=10)
        events_response.raise_for_status()
        
        events = events_response.json()
        
        # Process each event region
        for event_region, region_events in events.items():
            for event in region_events:
                # Check if event is active (status "1")
                if event.get("status") == "1":
                    # Extract event details
                    affected_services = []
                    for service_key, service_info in event.get("impacted_services", {}).items():
                        affected_services.append(service_info.get("service_name", service_key))
                    
                    # Extract latest message
                    latest_message = ""
                    if event.get("event_log") and len(event["event_log"]) > 0:
                        latest_log = event["event_log"][0]  # Most recent log entry
                        latest_message = latest_log.get("message", "")
                    
                    # Get timestamps
                    start_time = datetime.now(timezone.utc)
                    if event.get("start_time"):
                        try:
                            start_time = datetime.fromtimestamp(
                                int(event["start_time"]), timezone.utc
                            )
                        except (ValueError, TypeError):
                            pass
                    
                    # Determine status level based on impact
                    status_level = StatusLevel.DEGRADED
                    if event.get("impact") == "CRITICAL":
                        status_level = StatusLevel.OUTAGE

                    # Create incident report
                    incident = IncidentReport(
                        id=event.get("event_id", "unknown"),
                        provider_name=self.config.name,
                        title=event.get("event_title", "AWS Service Issue"),
                        status_level=status_level,
                        started_at=start_time,
                        resolved_at=None,
                        description=latest_message
                    )
                    
                    incidents.append(incident)
        
        return incidents
    
    def _parse_events(self, events: Dict[str, List[Dict[str, Any]]]) -> ServiceStatus:
        """Parse AWS current events to determine service status"""
        # Implementation would extract active regions, services, and status levels
        # This is a simplified version - you'd want more robust parsing in production
        
        status_level = StatusLevel.OPERATIONAL
        affected_services = []
        latest_message = ""
        
        # Iterate through events to find latest and most severe
        for event_region, region_events in events.items():
            for event in region_events:
                # Check if event is active (status "1")
                if event.get("status") == "1":
                    # Determine severity based on impact
                    impact = event.get("impact", "").upper()
                    current_status = StatusLevel.DEGRADED
                    
                    # Critical impact should be mapped to OUTAGE
                    if impact == "CRITICAL":
                        current_status = StatusLevel.OUTAGE
                        
                    # Use the most severe status found
                    if current_status.value > status_level.value:
                        status_level = current_status
                    
                    # Add affected services to our list
                    for service_key, service_info in event.get("impacted_services", {}).items():
                        affected_services.append(service_info.get("service_name", service_key))
                    
                    # Get the latest message
                    if event.get("event_log") and len(event["event_log"]) > 0:
                        latest_log = event["event_log"][0]  # Most recent log entry
                        latest_message = latest_log.get("message", "")
        
        # If any services are affected, return the appropriate status
        if affected_services:
            message = f"{'Outage' if status_level == StatusLevel.OUTAGE else 'Degraded performance'}: {', '.join(affected_services)}. {latest_message}"
            return ServiceStatus(
                provider_name=self.config.name,
                category=self.config.category,
                status_level=status_level,
                last_checked=datetime.now(timezone.utc),
                message=message
            )
        
        # Fallback if we can't determine status from events
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All services operational"
        )
    
    def _parse_announcement(self, announcement: Dict[str, Any]) -> ServiceStatus:
        """Parse AWS announcement to determine service status"""
        # If there's an announcement but no events, consider it a minor degradation
        # This would need to be adjusted based on actual announcement format
        description = announcement.get("description", "")
        
        if description:
            return ServiceStatus(
                provider_name=self.config.name,
                category=self.config.category,
                status_level=StatusLevel.DEGRADED,
                last_checked=datetime.now(timezone.utc),
                message=f"Service announcement: {description}"
            )
        
        # Fallback for empty announcement
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All services operational"
        )