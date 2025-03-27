from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

from application.interfaces.provider import StatusProvider, rate_limit
from domain.enums import StatusLevel
from domain.models import ServiceStatus

class AWSProvider(StatusProvider):
    """AWS Status Provider implementation using their health API endpoints"""
    
    def __init__(self):
        super().__init__(
            name="AWS",
            category="cloud",
            status_url="https://health.aws.amazon.com/health/status"
        )
        self._current_events_url = "https://health.aws.amazon.com/public/currentevents"
        self._announcement_url = "https://health.aws.amazon.com/public/announcement"
        
    @rate_limit(calls=1, period=60)  # Respect AWS API by limiting to 1 call per minute
    def get_status(self) -> ServiceStatus:
        """Fetch AWS current service status"""
        try:
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
                provider=self.name,
                category=self.category,
                status=StatusLevel.OPERATIONAL,
                last_updated=datetime.now(timezone.utc),
                message="All AWS services operating normally"
            )
            
        except requests.RequestException as e:
            # Graceful degradation on connection errors
            # In a real implementation, you'd want to log this error
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=StatusLevel.UNKNOWN,
                last_updated=datetime.now(timezone.utc),
                message=f"Unable to fetch AWS status: {str(e)}"
            )
        except ValueError as e:
            # Handle JSON parsing errors
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=StatusLevel.UNKNOWN,
                last_updated=datetime.now(timezone.utc),
                message=f"Error parsing AWS status response: {str(e)}"
            )
    
    def _parse_events(self, events: List[Dict[str, Any]]) -> ServiceStatus:
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
                    status_level = StatusLevel.DEGRADED
                    
                    # Add affected services to our list
                    for service_key, service_info in event.get("impacted_services", {}).items():
                        affected_services.append(service_info.get("service_name", service_key))
                    
                    # Get the latest message
                    if event.get("event_log") and len(event["event_log"]) > 0:
                        latest_log = event["event_log"][0]  # Most recent log entry
                        latest_message = latest_log.get("message", "")
        
        # If any services are affected, return degraded status
        if affected_services:
            message = f"Degraded performance: {', '.join(affected_services)}. {latest_message}"
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=status_level,
                last_updated=datetime.now(timezone.utc),
                message=message
            )
        
        # Fallback if we can't determine status from events
        return ServiceStatus(
            provider=self.name,
            category=self.category,
            status=StatusLevel.OPERATIONAL,
            last_updated=datetime.now(timezone.utc),
            message="All services operational"
        )
    
    def _parse_announcement(self, announcement: Dict[str, Any]) -> ServiceStatus:
        """Parse AWS announcement to determine service status"""
        # If there's an announcement but no events, consider it a minor degradation
        # This would need to be adjusted based on actual announcement format
        description = announcement.get("description", "")
        
        if description:
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=StatusLevel.DEGRADED,
                last_updated=datetime.now(timezone.utc),
                message=f"Service announcement: {description}"
            )
        
        # Fallback for empty announcement
        return ServiceStatus(
            provider=self.name,
            category=self.category,
            status=StatusLevel.OPERATIONAL,
            last_updated=datetime.now(timezone.utc),
            message="All services operational"
        )