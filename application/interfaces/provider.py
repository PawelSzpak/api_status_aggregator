from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, TypeVar, Callable, Any, Dict
import time
import logging
import threading

from domain import ServiceStatus, ProviderConfiguration, IncidentReport

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Global registry to track rate limit state per provider class
# Using class name as key to avoid memory leaks from instance references
_rate_limit_registry: Dict[str, Dict[str, Any]] = {}
_registry_lock = threading.RLock()

def rate_limit(calls: int, period: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Rate limiting decorator to prevent overwhelming status pages.
    
    Args:
        calls: Maximum number of calls allowed in the period
        period: Time period in seconds
        
    Returns:
        Decorator function that applies rate limiting
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get the instance and its class
            instance = args[0]
            class_name = instance.__class__.__name__
            
            # Create a unique key for this method on this class
            method_key = f"{class_name}.{func.__name__}"
            
            with _registry_lock:
                # Initialize state if not exists
                if method_key not in _rate_limit_registry:
                    _rate_limit_registry[method_key] = {
                        'last_reset': datetime.now(timezone.utc),
                        'calls_made': 0
                    }
                
                state = _rate_limit_registry[method_key]
                now = datetime.now(timezone.utc)
                
                # Reset counter if period has elapsed
                elapsed = (now - state['last_reset']).total_seconds()
                if elapsed > period:
                    state['calls_made'] = 0
                    state['last_reset'] = now
                
                # Check if we've reached the limit
                if state['calls_made'] >= calls:
                    sleep_time = period - elapsed
                    if sleep_time > 0:
                        logger.warning(f"Rate limit reached for {method_key}, sleeping for {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                    # Reset after sleeping
                    state['calls_made'] = 0
                    state['last_reset'] = datetime.now(timezone.utc)
                
                # Increment counter and call the wrapped function
                state['calls_made'] += 1
                
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


class StatusProvider(ABC):
    """Abstract base class defining the interface for status providers."""
    
    def __init__(self, config: ProviderConfiguration) -> None:
        self.config = config
        self._last_status: Optional[ServiceStatus] = None
        self._last_active_incidents: Optional[list[IncidentReport]] = None
        
    @abstractmethod
    def _fetch_current_status(self) -> ServiceStatus:
        """Fetch and parse the current service status.
        
        Returns:
            ServiceStatus: The current status of the service
            
        Raises:
            ConnectionError: If the status page cannot be reached
            ValueError: If the status page structure is invalid
        """
        pass
        
    @abstractmethod
    def _fetch_active_incidents(self) -> list[IncidentReport]:
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
            status = self._fetch_current_status()
            self._last_status = status
            return status
        except Exception as e:
            logger.error(f"Error fetching status for {self.config.name}: {str(e)}")
            if self._last_status:
                return self._last_status
            raise


    @rate_limit(calls=12, period=60)
    def get_incidents(self) -> list[IncidentReport]:
        """Get the active incidents with rate limiting and error handling.
        
        Returns:
            list[IncidentReport]: Currently active incidents
            
        Note:
            This method implements rate limiting and will block if the limit is exceeded.
            On errors, it returns the last known active incidents if available.
        """
        try:
            active_incidents = self._fetch_active_incidents()
            self._last_active_incidents = active_incidents
            return active_incidents
        except Exception as e:
            logger.error(f"Error fetching active incidents for {self.config.name}: {str(e)}")
            if self._last_active_incidents:
                return self._last_active_incidents
            raise
            