"""
Database connection and session management for the API Status Aggregator.
"""

import logging
import os
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

# Create declarative base for models
Base = declarative_base()

# Global engine reference
_engine = None
Session = None

def init_db():
    """Initialize the database connection."""
    global _engine, Session
    
    # Get database URL from environment or use default
    database_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/status_dashboard')
    
    try:
        # Create engine with connection pooling
        _engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800  # Recycle connections after 30 minutes
        )
        
        # Create session factory
        session_factory = sessionmaker(bind=_engine)
        Session = scoped_session(session_factory)
        
        # Create all tables if they don't exist
        Base.metadata.create_all(_engine)
        
        logger.info(f"Database initialized at {database_url}")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

def get_session():
    """Get a scoped database session.
    
    Returns:
        SQLAlchemy session object
    """
    global Session
    
    if Session is None:
        init_db()
        
    return Session()

def dispose_engine():
    """Dispose of the database engine."""
    global _engine
    
    if _engine is not None:
        _engine.dispose()
        logger.info("Database engine disposed")