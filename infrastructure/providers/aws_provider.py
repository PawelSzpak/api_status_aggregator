from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from domain.enums import StatusLevel
from domain.models import ServiceStatus
from application.interfaces.provider import StatusProvider, rate_limit


class AWSStatusProvider(StatusProvider):
    """AWS Status provider with configurable service monitoring."""
    
    def __init__(self, services_to_monitor: Optional[List[str]] = None):
        """
        Initialize AWS status provider with optional service filtering.
        
        Args:
            services_to_monitor: List of AWS service names to monitor.
                                If None, will monitor a default set of common services.
        """
        super().__init__(
            name="AWS",
            category="cloud",
            status_url="https://health.aws.amazon.com/health/status"
        )
        # Default to monitoring common services if none specified
        self.services_to_monitor = services_to_monitor or [
            "EC2", "S3", "RDS", "Lambda", "DynamoDB", 
            "CloudFront", "Route 53", "SQS", "SNS"
        ]
    
    @rate_limit(calls=1, period=300)  # Limit to 1 call per 5 minutes
    def get_status(self) -> ServiceStatus:
        """
        Fetch AWS service status for configured services.
        
        Returns:
            ServiceStatus: Aggregated status with worst status level across monitored services.
        """
        try:
            response = requests.get(self.status_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            service_statuses = self._parse_service_statuses(soup)
            
            # Filter to only include services we're monitoring
            monitored_statuses = {
                service: status 
                for service, status in service_statuses.items()
                if service in self.services_to_monitor
            }
            
            # Determine overall status (worst status of any monitored service)
            overall_status = self._determine_overall_status(monitored_statuses)
            
            # Generate status message
            message = self._generate_status_message(monitored_statuses)
            
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=overall_status,
                last_updated=datetime.utcnow(),
                message=message,
                details=monitored_statuses
            )
            
        except Exception as e:
            # Log the error properly
            import logging
            logging.error(f"Error fetching AWS status: {str(e)}")
            
            # Return degraded status when we can't check
            return ServiceStatus(
                provider=self.name,
                category=self.category,
                status=StatusLevel.UNKNOWN,
                last_updated=datetime.utcnow(),
                message=f"Unable to fetch AWS status: {str(e)}"
            )
    
    def _parse_service_statuses(self, soup: BeautifulSoup) -> Dict[str, StatusLevel]:
        """
        Parse the AWS status page to extract service statuses.
        
        Args:
            soup: BeautifulSoup object of the AWS status page
            
        Returns:
            Dict mapping service names to their StatusLevel
        """
        service_statuses = {}
        
        # This is a simplified example - actual implementation would need to
        # navigate AWS's HTML structure to find service status indicators
        service_rows = soup.select('.aws-service-row')  # Adjust selector based on actual page structure
        
        for row in service_rows:
            service_name_elem = row.select_one('.service-name')
            status_elem = row.select_one('.service-status')
            
            if service_name_elem and status_elem:
                service_name = service_name_elem.text.strip()
                status_text = status_elem.text.strip().lower()
                
                # Map AWS status indicators to our status levels
                status = StatusLevel.OPERATIONAL
                if "degraded" in status_text or "performance" in status_text:
                    status = StatusLevel.DEGRADED
                elif "outage" in status_text or "unavailable" in status_text:
                    status = StatusLevel.OUTAGE
                
                service_statuses[service_name] = status
        
        return service_statuses
    
    def _determine_overall_status(self, service_statuses: Dict[str, StatusLevel]) -> StatusLevel:
        """
        Determine overall status based on individual service statuses.
        The overall status is the worst status of any monitored service.
        
        Args:
            service_statuses: Dict mapping service names to StatusLevel
            
        Returns:
            StatusLevel representing overall status
        """
        if not service_statuses:
            return StatusLevel.UNKNOWN
            
        # Status severity order: OPERATIONAL < DEGRADED < OUTAGE
        if any(status == StatusLevel.OUTAGE for status in service_statuses.values()):
            return StatusLevel.OUTAGE
        elif any(status == StatusLevel.DEGRADED for status in service_statuses.values()):
            return StatusLevel.DEGRADED
        return StatusLevel.OPERATIONAL
    
    def _generate_status_message(self, service_statuses: Dict[str, StatusLevel]) -> str:
        """
        Generate a human-readable status message.
        
        Args:
            service_statuses: Dict mapping service names to StatusLevel
            
        Returns:
            String message summarizing service statuses
        """
        if not service_statuses:
            return "No monitored AWS services found"
            
        # Count services in each status
        operational_count = sum(1 for status in service_statuses.values() 
                               if status == StatusLevel.OPERATIONAL)
        degraded_count = sum(1 for status in service_statuses.values() 
                            if status == StatusLevel.DEGRADED)
        outage_count = sum(1 for status in service_statuses.values() 
                          if status == StatusLevel.OUTAGE)
        
        # Generate appropriate message
        if outage_count > 0:
            outage_services = [service for service, status in service_statuses.items() 
                              if status == StatusLevel.OUTAGE]
            return f"Outage detected in {', '.join(outage_services)}"
        elif degraded_count > 0:
            degraded_services = [service for service, status in service_statuses.items() 
                                if status == StatusLevel.DEGRADED]
            return f"Degraded performance in {', '.join(degraded_services)}"
        else:
            return f"All {len(service_statuses)} monitored AWS services operational"