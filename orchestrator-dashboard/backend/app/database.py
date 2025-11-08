"""Database models and configuration for the orchestration layer."""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orchestrator.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class RemovalRequest(Base):
    """Tracks high-level feature flag removal requests from users."""
    
    __tablename__ = "removal_requests"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    flag_key = Column(String, nullable=False, index=True)
    repositories = Column(Text, nullable=False)  # JSON array of repository URLs
    feature_flag_provider = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued", index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    total_acu_consumed = Column(Integer, default=0)
    
    sessions = relationship("DevinSession", back_populates="removal_request", cascade="all, delete-orphan")


class DevinSession(Base):
    """Tracks individual Devin sessions (one per repository in a removal request)."""
    
    __tablename__ = "devin_sessions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    removal_request_id = Column(Integer, ForeignKey("removal_requests.id"), nullable=False, index=True)
    repository = Column(String, nullable=False)
    devin_session_id = Column(String, nullable=True, index=True)
    devin_session_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    pr_url = Column(String, nullable=True)
    structured_output = Column(Text, nullable=True)  # JSON
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    max_acu_limit = Column(Integer, default=500)
    acu_consumed = Column(Integer, nullable=True)
    
    removal_request = relationship("RemovalRequest", back_populates="sessions")
    
    logs = relationship("SessionLog", back_populates="session", cascade="all, delete-orphan")


class SessionLog(Base):
    """Stores log entries from Devin sessions for debugging and monitoring."""
    
    __tablename__ = "session_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    devin_session_id = Column(Integer, ForeignKey("devin_sessions.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    log_level = Column(String, nullable=False)  # info, warning, error, debug
    message = Column(Text, nullable=False)
    event_type = Column(String, nullable=True)  # status_change, message, error, pr_created
    
    session = relationship("DevinSession", back_populates="logs")


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
