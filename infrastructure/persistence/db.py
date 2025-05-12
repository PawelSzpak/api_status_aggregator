"""
Database connection and session management for the API Status Aggregator.
"""

import logging
import os
from typing import Optional
from datetime import timezone

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
        
    # Add dialect specification for psycopg v3 if not present
    if database_url.startswith('postgresql://') and not '+psycopg' in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://')

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
        
        from sqlalchemy import event
        from datetime import datetime, timedelta
        
        @event.listens_for(Session, 'before_flush')
        def delete_old_records(session, context, instances):
            """Delete records older than 90 days during each flush operation."""
            from infrastructure.persistence.models import StatusRecord
            retention_period = datetime.now(timezone.utc) - timedelta(days=90)
            
            # Use the session's query method directly
            old_records = session.query(StatusRecord).filter(
                StatusRecord.created_at < retention_period
            ).all()
            
            # Mark old records for deletion
            for record in old_records:
                session.delete(record)

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