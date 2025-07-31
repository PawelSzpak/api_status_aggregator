from datetime import datetime, timedelta, timezone
from typing import Optional, List
from dataclasses import dataclass
from .enums import StatusLevel, ServiceCategory

@dataclass
class ProviderConfiguration:
    """Configuration for a specific service provider."""
    name: str
    category: ServiceCategory
    status_url: str
    check_interval: timedelta = timedelta(minutes=5)
    timeout: timedelta = timedelta(seconds=30)

@dataclass
class IncidentReport:
    """Represents a reported service incident."""
    id: str
    provider_name: str
    status_level: StatusLevel
    started_at: datetime
    resolved_at: Optional[datetime]
    title: str
    description: Optional[str] = None
    updates: List[str] = None

    def __post_init__(self):
        """Initialize the updates list if none provided."""
        if self.updates is None:
            self.updates = []
        
        if self.resolved_at and self.resolved_at < self.started_at:
            raise ValueError("Incident resolution time cannot be before start time")

    @property
    def is_active(self) -> bool:
        """Indicates if this incident is currently ongoing."""
        return self.resolved_at is None

    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate the incident duration if resolved."""
        if not self.resolved_at:
            return None
        return self.resolved_at - self.started_at
