from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, TypeVar, Callable, Any
import time
import logging

from domain import ServiceStatus, ProviderConfiguration, IncidentReport

logger = logging.getLogger(__name__)

T = TypeVar('T')

def rate_limit(calls: int, period: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Rate limiting decorator to prevent overwhelming status pages.
    
    Args:
        calls: Maximum number of calls allowed in the period
        period: Time period in seconds
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        last_reset = datetime.now(timezone.utc)
        calls_made = 0

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            nonlocal last_reset, calls_made
            
            now = datetime.now(timezone.utc)
            if now - last_reset > timedelta(seconds=period):
                calls_made = 0
                last_reset = now
                
            if calls_made >= calls:
                sleep_time = period - (now - last_reset).total_seconds()
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                calls_made = 0
                last_reset = datetime.now(timezone.utc)
                
            calls_made += 1
            return func(*args, **kwargs)
            
        return wrapper
    return decorator

class StatusProvider(ABC):
    """Abstract base class defining the interface for status providers."""
    
    def __init__(self, config: ProviderConfiguration) -> None:
        self.config = config
        self._last_status: Optional[ServiceStatus] = None
        
    @abstractmethod
    def fetch_current_status(self) -> ServiceStatus:
        """Fetch and parse the current service status.
        
        Returns:
            ServiceStatus: The current status of the service
            
        Raises:
            ConnectionError: If the status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        pass
        
    @abstractmethod
    def fetch_active_incidents(self) -> list[IncidentReport]:
        """Fetch any active incidents from the provider.
        
        Returns:
            list[IncidentReport]: Currently active incidents
            
        Raises:
            ConnectionError: If the incidents page cannot be reached
            ValueError: If the incident page structure is invalid
        """
        pass
        
    @property
    def last_known_status(self) -> Optional[ServiceStatus]:
        """Retrieve the last successfully fetched status."""
        return self._last_status
        
    @rate_limit(calls=12, period=60)
    def get_status(self) -> ServiceStatus:
        """Get the current status with rate limiting and error handling.
        
        Returns:
            ServiceStatus: Current or last known status
            
        Note:
            This method implements rate limiting and will block if the limit is exceeded.
            On errors, it returns the last known status if available.
        """
        try:
            status = self.fetch_current_status()
            self._last_status = status
            return status
        except Exception as e:
            logger.error(f"Error fetching status for {self.config.name}: {str(e)}")
            if self._last_status:
                return self._last_status
            raise