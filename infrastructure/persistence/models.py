from .db import Base
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Index, event
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from domain.enums import StatusLevel, ServiceCategory
from .db import Session

# Create PostgreSQL ENUM types explicitly with the correct values
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# Define the PostgreSQL enums with explicit values
servicecategory_enum = ENUM(
    'payment', 'authentication', 'cloud',
    name='servicecategory'
)

statuslevel_enum = ENUM(
    'operational', 'degraded', 'outage', 'unknown',
    name='statuslevel'
)

class StatusRecord(Base):
    """Status history for each provider."""
    __tablename__ = 'status_records'
    
    id = Column(Integer, primary_key=True)
    provider_name = Column(String(100), nullable=False)
    # Use the explicit PostgreSQL enum
    category = Column(servicecategory_enum, nullable=False)
    status = Column(statuslevel_enum, nullable=False)
    message = Column(Text, nullable=True)
    incident_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    
    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_provider_created', provider_name, created_at),
        Index('idx_category_status', category, status),
    )
    
    def __repr__(self) -> str:
        return f"<StatusRecord(provider='{self.provider_name}', status='{self.status}', created='{self.created_at}')>"

class IncidentRecord(Base):
    """Records of service incidents."""
    __tablename__ = 'incident_records'
    
    id = Column(String(100), primary_key=True)
    provider_name = Column(String(100), nullable=False)
    status = Column(statuslevel_enum, nullable=False)
    started_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Relationship to incident updates
    updates = relationship("IncidentUpdate", back_populates="incident", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<IncidentRecord(id='{self.id}', provider='{self.provider_name}', title='{self.title}')>"

class IncidentUpdate(Base):
    """Updates for an ongoing incident."""
    __tablename__ = 'incident_updates'
    
    id = Column(Integer, primary_key=True)
    incident_id = Column(String(100), ForeignKey('incident_records.id'), nullable=False)
    content = Column(Text, nullable=False)
    posted_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    
    # Relationship to parent incident
    incident = relationship("IncidentRecord", back_populates="updates")
    
    def __repr__(self) -> str:
        return f"<IncidentUpdate(incident='{self.incident_id}', posted='{self.posted_at}')>"