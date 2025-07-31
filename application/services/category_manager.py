from typing import Dict, List, Optional, Set
import logging
from datetime import datetime, timezone
from collections import defaultdict

from application.interfaces import StatusProvider
from domain.enums import ServiceCategory, StatusLevel, ServiceStatus


logger = logging.getLogger(__name__)

class CategoryManager:
    """
    Manages provider organization and status aggregation.
    Serves as the interface between individual providers and the presentation layer.
    """
    
    def __init__(self) -> None:
        """Initialize the category manager with empty provider collections."""
        self._providers: Dict[str, StatusProvider] = {}
        self._category_providers: Dict[ServiceCategory, Set[str]] = defaultdict(set)
        self._last_update = datetime.now(timezone.utc)
    
    def register_provider(self, provider: StatusProvider) -> None:
        """
        Register a provider with the manager.
        
        Args:
            provider: The provider to register
            
        Raises:
            ValueError: If a provider with the same name is already registered
        """
        if provider.config.name in self._providers:
            raise ValueError(f"Provider '{provider.config.name}' is already registered")
        
        self._providers[provider.config.name] = provider
        self._category_providers[provider.config.category].add(provider.config.name)
        logger.info(f"Registered provider: {provider.config.name} in category {provider.config.category.value}")
    
    def get_all_providers(self) -> List[StatusProvider]:
        """Get all registered providers."""
        return list(self._providers.values())
    
    def get_providers_by_category(self, category: ServiceCategory) -> List[StatusProvider]:
        """
        Get all providers in a specific category.
        
        Args:
            category: The category to filter by
            
        Returns:
            List[StatusProvider]: Providers in the specified category
        """
        provider_names = self._category_providers.get(category, set())
        return [self._providers[name] for name in provider_names]
    
    def get_provider(self, name: str) -> Optional[StatusProvider]:
        """
        Get a specific provider by name.
        
        Args:
            name: Name of the provider to retrieve
            
        Returns:
            Optional[StatusProvider]: The provider if found, None otherwise
        """
        return self._providers.get(name)
    
    def get_all_statuses(self) -> List[ServiceStatus]:
        """
        Get the current status of all registered providers.
        
        Returns:
            List[ServiceStatus]: Current status of all providers
        """
        statuses = []
        
        for provider in self._providers.values():
            try:
                status = provider.get_status()
                statuses.append(status)
            except Exception as e:
                logger.error(f"Failed to get status for {provider.config.name}: {str(e)}")
                # If the provider has a last known status, use that
                if provider.last_known_status:
                    statuses.append(provider.last_known_status)
        
        self._last_update = datetime.now(timezone.utc)
        return statuses
    
    def get_category_statuses(self, category: ServiceCategory) -> List[ServiceStatus]:
        """
        Get statuses for all providers in a specific category.
        
        Args:
            category: The category to get statuses for
            
        Returns:
            List[ServiceStatus]: Current status of providers in the category
        """
        providers = self.get_providers_by_category(category)
        statuses = []
        
        for provider in providers:
            try:
                status = provider.get_status()
                statuses.append(status)
            except Exception as e:
                logger.error(f"Failed to get status for {provider.config.name}: {str(e)}")
                if provider.last_known_status:
                    statuses.append(provider.last_known_status)
        
        return statuses
    
    def get_category_summary(self, category: ServiceCategory) -> StatusLevel:
        """
        Get the overall status for a category.
        
        Args:
            category: The category to summarize
            
        Returns:
            StatusLevel: The worst status level among providers in the category
        """
        statuses = self.get_category_statuses(category)
        
        if not statuses:
            return StatusLevel.UNKNOWN
        
        # Return the worst status in the category
        # OPERATIONAL < DEGRADED < OUTAGE
        if any(s.status_level == StatusLevel.OUTAGE for s in statuses):
            return StatusLevel.OUTAGE
        elif any(s.status_level == StatusLevel.DEGRADED for s in statuses):
            return StatusLevel.DEGRADED
        elif all(s.status_level == StatusLevel.OPERATIONAL for s in statuses):
            return StatusLevel.OPERATIONAL
        else:
            return StatusLevel.UNKNOWN
    
    def get_overall_summary(self) -> Dict[ServiceCategory, StatusLevel]:
        """
        Get a summary of all categories.
        
        Returns:
            Dict[ServiceCategory, StatusLevel]: Status summary for each category
        """
        return {
            category: self.get_category_summary(category)
            for category in ServiceCategory
        }
    
    @property
    def last_update_time(self) -> datetime:
        """Get the time of the last status update."""
        return self._last_update