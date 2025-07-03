from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
import requests
import logging

from application.interfaces.provider import StatusProvider, rate_limit
from domain import ServiceStatus, StatusLevel, IncidentReport, ProviderConfiguration, ServiceCategory

logger = logging.getLogger(__name__)

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
        
        # Handle different response formats:
        # Format 1: [] (empty list when no events)
        # Format 2: [events...] (list of events) 
        # Format 3: {"region": [events]} (dictionary keyed by region - legacy support)
        
        event_list = []
        
        if isinstance(events, list):
            # Format 1 & 2: It's already a list (empty or with events)
            event_list = events
        elif isinstance(events, dict):
            # Format 3: Dictionary keyed by region - flatten to list
            for region_events in events.values():
                if isinstance(region_events, list):
                    event_list.extend(region_events)
        else:
            # Unexpected format - log and continue
            logger.warning(f"Unexpected AWS events format: {type(events)}")
        
        # Process each event
        for event in event_list:
            # Check if event is active
            # status "1" = active, "0" = resolved
            # Also check if there's no end_time (ongoing)
            is_active = (event.get("status") == "1" or 
                        event.get("status") == 1 or
                        (not event.get("end_time") and event.get("date")))
            
            if is_active:
                # Extract service name
                service_name = event.get("service_name", event.get("service", "Unknown Service"))
                
                # Extract latest message from event_log
                latest_message = ""
                event_log = event.get("event_log", [])
                if event_log and len(event_log) > 0:
                    # Get the most recent log entry (last in the list)
                    latest_log = event_log[-1]
                    latest_message = latest_log.get("message", "")
                
                # Get timestamps
                start_time = datetime.now(timezone.utc)
                if event.get("date"):
                    try:
                        start_time = datetime.fromtimestamp(
                            int(event["date"]), timezone.utc
                        )
                    except (ValueError, TypeError):
                        pass
                
                # Parse resolved time if available
                resolved_at = None
                if event.get("end_time"):
                    try:
                        resolved_at = datetime.fromtimestamp(
                            int(event["end_time"]), timezone.utc
                        )
                    except (ValueError, TypeError):
                        pass
                
                # Determine status level based on summary/title
                summary = event.get("summary", "").upper()
                status_level = StatusLevel.DEGRADED
                
                if "CRITICAL" in summary or "OUTAGE" in summary:
                    status_level = StatusLevel.OUTAGE
                elif "RESOLVED" in summary:
                    status_level = StatusLevel.OPERATIONAL
                    resolved_at = resolved_at or datetime.now(timezone.utc)

                # Create incident report
                incident = IncidentReport(
                    id=event.get("arn", "unknown"),
                    provider_name=self.config.name,
                    title=event.get("summary", "AWS Service Issue"),
                    status_level=status_level,
                    started_at=start_time,
                    resolved_at=resolved_at,
                    description=latest_message
                )
                
                incidents.append(incident)
        
        return incidents
    
    def _parse_events(self, events: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]) -> ServiceStatus:
        """Parse AWS current events to determine service status.
        
        Args:
            events: Either a list of events or a dictionary keyed by region
            
        Returns:
            ServiceStatus: Current service status
        """
        status_level = StatusLevel.OPERATIONAL
        affected_services = []
        latest_message = ""
        active_count = 0
        
        # Normalize events to a list format
        event_list = []
        
        if isinstance(events, list):
            event_list = events
        elif isinstance(events, dict):
            # Flatten dictionary format to list
            for region_events in events.values():
                if isinstance(region_events, list):
                    event_list.extend(region_events)
        
        # Iterate through events to find active ones and assess severity
        for event in event_list:
            # Check if event is active (status "1" or no end_time)
            is_active = (event.get("status") == "1" or 
                        event.get("status") == 1 or
                        (not event.get("end_time") and event.get("date")))
            
            if is_active:
                active_count += 1
                
                # Get service name
                service_name = event.get("service_name", event.get("service", "Unknown Service"))
                if service_name not in affected_services:
                    affected_services.append(service_name)
                
                # Determine severity based on summary
                summary = event.get("summary", "").upper()
                current_status = StatusLevel.DEGRADED
                
                if "CRITICAL" in summary or "OUTAGE" in summary:
                    current_status = StatusLevel.OUTAGE
                    
                # Use the most severe status found
                if current_status == StatusLevel.OUTAGE or (current_status == StatusLevel.DEGRADED and status_level == StatusLevel.OPERATIONAL):
                    status_level = current_status
                
                # Get the latest message from event_log
                event_log = event.get("event_log", [])
                if event_log and len(event_log) > 0:
                    latest_log = event_log[-1]  # Most recent log entry
                    latest_message = latest_log.get("message", "")
        
        # If any services are affected, return the appropriate status
        if active_count > 0:
            status_name = "Outage" if status_level == StatusLevel.OUTAGE else "Service issues"
            services_text = ", ".join(affected_services[:3])  # Show first 3 services
            if len(affected_services) > 3:
                services_text += f" and {len(affected_services) - 3} more"
            
            message = f"{status_name} affecting {services_text}. {latest_message[:100]}{'...' if len(latest_message) > 100 else ''}"
            return ServiceStatus(
                provider_name=self.config.name,
                category=self.config.category,
                status_level=status_level,
                last_checked=datetime.now(timezone.utc),
                message=message
            )
        
        # No active events - all operational
        return ServiceStatus(
            provider_name=self.config.name,
            category=self.config.category,
            status_level=StatusLevel.OPERATIONAL,
            last_checked=datetime.now(timezone.utc),
            message="All AWS services operating normally"
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