"""
Background scheduler for periodic API status checks.

This module implements a centralized scheduler using APScheduler to periodically
fetch status updates from all registered providers.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from application.services.category_manager import CategoryManager
from infrastructure.persistence.models import StatusRecord
from infrastructure.persistence.db import get_session

logger = logging.getLogger(__name__)

class StatusScheduler:
    """Manages periodic status checks for all registered providers."""
    
    _instance: Optional['StatusScheduler'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Implement singleton pattern to ensure only one scheduler instance exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(StatusScheduler, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Initialize the scheduler if not already initialized."""
        if self._initialized:
            return
            
        # Define scheduler configuration
        jobstores = {'default': MemoryJobStore()}
        executors = {'default': ThreadPoolExecutor(20)}
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 60  # Allow jobs to run up to 60s late
        }
        
        # Create the scheduler
        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )
        
        # Internal state
        self._category_manager: Optional[CategoryManager] = None
        self._latest_data: Dict[str, Any] = {
            'providers': [],
            'categories': {},
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'error': None
        }
        self._data_lock = threading.RLock()
        self._initialized = True
        
        logger.info("Status scheduler initialized")
    
    def set_category_manager(self, category_manager: CategoryManager) -> None:
        """Set the category manager to use for status updates.
        
        Args:
            category_manager: The category manager instance
        """
        self._category_manager = category_manager
    
    def start(self, check_interval: int = 300) -> None:
        """Start the background scheduler.
        
        Args:
            check_interval: Interval between checks in seconds (default: 5 minutes)
        
        Raises:
            RuntimeError: If category manager is not set
        """
        if not self._category_manager:
            raise RuntimeError("Category manager must be set before starting scheduler")
        
        # Register the update job to run at the specified interval
        self._scheduler.add_job(
            self._update_all_statuses,
            trigger=IntervalTrigger(seconds=check_interval),
            id='update_statuses',
            replace_existing=True
        )
        
        # Start the scheduler
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info(f"Status scheduler started with check interval of {check_interval} seconds")
            
            # Run initial status update
            self._update_all_statuses()
    
    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Status scheduler shutdown")
    
    def get_latest_data(self) -> Dict[str, Any]:
        """Get the latest status data.
        
        Returns:
            Dict containing the latest provider statuses and category summaries
        """
        with self._data_lock:
            return self._latest_data.copy()
    
    def force_update(self) -> Dict[str, Any]:
        """Force an immediate status update.
        
        Returns:
            Dict containing the updated status data
        """
        self._update_all_statuses()
        return self.get_latest_data()
    
    def _update_all_statuses(self) -> None:
        """Update status for all providers and store the results."""
        if not self._category_manager:
            logger.error("Category manager not set, cannot update statuses")
            return
            
        try:
            logger.info("Starting status update for all providers")
            
            # Get all current statuses
            all_statuses = self._category_manager.get_all_statuses()
            
            # Get category summaries
            category_summaries = self._category_manager.get_overall_summary()
            
            # Store in database (if implemented)
            try:
                self._store_status_records(all_statuses)
            except Exception as db_error:
                logger.error(f"Failed to store status records: {str(db_error)}")
            
            # Format and update the cached data
            with self._data_lock:
                self._latest_data = {
                    'providers': [
                        {
                            'name': status.provider_name,
                            'category': status.category.value,
                            'status': status.status_level.value,
                            'message': status.message,
                            'last_checked': status.last_checked.isoformat()
                        }
                        for status in all_statuses
                    ],
                    'categories': {
                        category.value: status_level.value
                        for category, status_level in category_summaries.items()
                    },
                    'last_updated': datetime.now(timezone.utc).isoformat(),
                    'error': None
                }
                
            logger.info(f"Status update completed for {len(all_statuses)} providers")
            
        except Exception as e:
            logger.exception(f"Error updating statuses: {str(e)}")
            
            # Update error state in cached data
            with self._data_lock:
                self._latest_data['error'] = f"Failed to update: {str(e)}"
                self._latest_data['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    def _store_status_records(self, statuses) -> None:
        """Store status records in the database.
        
        Args:
            statuses: List of ServiceStatus objects to store
        """
        # This method would normally store the status records in the database
        # For now, we'll leave it as a placeholder since we don't have full DB implementation
        session = get_session()
        try:
            for status in statuses:
                record = StatusRecord(
                    provider_name=status.provider_name,
                    category=status.category.value,
                    status=status.status_level.value,
                    message=status.message,
                    created_at=status.last_checked
                )
                session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


# Create a global scheduler instance
scheduler = StatusScheduler()