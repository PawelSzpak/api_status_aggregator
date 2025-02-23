from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class StatusLevel(Enum):
    """Represents the operational status of a service."""
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OUTAGE = "outage"
    UNKNOWN = "unknown"

    @property
    def is_problematic(self) -> bool:
        """Indicates whether this status level represents a problem state."""
        return self in (StatusLevel.DEGRADED, StatusLevel.OUTAGE)

class ServiceCategory(Enum):
    """Categories of services being monitored."""
    PAYMENT = "payment"
    AUTHENTICATION = "authentication"
    CLOUD = "cloud"

@dataclass(frozen=True)
class ServiceStatus:
    """Immutable value object representing a service's current status."""
    provider_name: str
    category: ServiceCategory
    status_level: StatusLevel
    last_checked: datetime
    message: Optional[str] = None
    incident_id: Optional[str] = None

    def __post_init__(self):
        """Validate the status data."""
        if not self.provider_name:
            raise ValueError("Provider name cannot be empty")
        if not isinstance(self.category, ServiceCategory):
            raise ValueError("Category must be a ServiceCategory enum")
        if not isinstance(self.status_level, StatusLevel):
            raise ValueError("Status must be a StatusLevel enum")
        if not isinstance(self.last_checked, datetime):
            raise ValueError("Last checked must be a datetime")