"""
Feature Flag Removal Orchestration Dashboard - Lightweight Backend
Single-file FastAPI application with all functionality consolidated.
"""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, validator, model_validator, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import logging
import os
import time
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orchestrator.db")
MAX_REPOS_PER_REQUEST = 5
MAX_CONCURRENT_SESSIONS = 20
POLL_INTERVAL = 10  # seconds
TIMEOUT_THRESHOLD = 900  # 15 minutes in seconds

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
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True)
    feature_flag_provider = Column(String, nullable=True)
    preserve_mode = Column(String, nullable=False, default="enabled")
    status = Column(String, nullable=False, default="queued", index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    total_acu_consumed = Column(Integer, default=0)
    
    repository = relationship("Repository", back_populates="removal_requests")
    sessions = relationship("DevinSession", back_populates="removal_request", cascade="all, delete-orphan")


class DevinSession(Base):
    """Tracks individual Devin sessions (one per repository in a removal request)."""
    
    __tablename__ = "devin_sessions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    removal_request_id = Column(Integer, ForeignKey("removal_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    repository = Column(String, nullable=False)
    devin_session_id = Column(String, nullable=True, index=True)
    devin_session_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    pr_url = Column(String, nullable=True)
    structured_output = Column(Text, nullable=True)
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


class Repository(Base):
    """Tracks registered repositories for flag discovery and removal."""
    
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    url = Column(String, nullable=False, unique=True, index=True)
    github_token = Column(String, nullable=True)  # For private repos, never returned in API
    provider_detected = Column(String, nullable=True)  # LaunchDarkly, Statsig, etc.
    last_scanned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    discovered_flags = relationship("DiscoveredFlag", back_populates="repository", cascade="all, delete-orphan")
    removal_requests = relationship("RemovalRequest", back_populates="repository")


class DiscoveredFlag(Base):
    """Stores flags discovered during repository scans."""
    
    __tablename__ = "discovered_flags"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False, index=True)
    flag_key = Column(String, nullable=False, index=True)
    occurrences = Column(Integer, nullable=False, default=0)
    files = Column(Text, nullable=True)  # JSON array of file paths
    provider = Column(String, nullable=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    repository = relationship("Repository", back_populates="discovered_flags")
    
    __table_args__ = (
        UniqueConstraint('repository_id', 'flag_key', name='uix_repo_flag'),
    )


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)
    
    if "sqlite" in DATABASE_URL:
        migrations = [
            ("preserve_mode", "ALTER TABLE removal_requests ADD COLUMN preserve_mode TEXT DEFAULT 'enabled' NOT NULL"),
            ("repository_id", "ALTER TABLE removal_requests ADD COLUMN repository_id INTEGER")
        ]
        
        for column_name, sql in migrations:
            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Added {column_name} column to removal_requests table")
            except Exception as e:
                if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
                    logger.warning(f"Could not add {column_name} column (may already exist): {e}")
        
        try:
            with engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(devin_sessions)")).fetchall()
                removal_request_id_col = next((col for col in result if col[1] == 'removal_request_id'), None)
                
                if removal_request_id_col and removal_request_id_col[3] == 1:
                    logger.info("Migrating devin_sessions table to make removal_request_id nullable")
                    
                    conn.execute(text("PRAGMA foreign_keys=OFF"))
                    conn.execute(text("""
                        CREATE TABLE devin_sessions_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            removal_request_id INTEGER,
                            repository TEXT NOT NULL,
                            devin_session_id TEXT,
                            devin_session_url TEXT,
                            status TEXT NOT NULL DEFAULT 'pending',
                            pr_url TEXT,
                            structured_output TEXT,
                            started_at DATETIME,
                            completed_at DATETIME,
                            error_message TEXT,
                            max_acu_limit INTEGER DEFAULT 500,
                            acu_consumed INTEGER,
                            FOREIGN KEY (removal_request_id) REFERENCES removal_requests(id) ON DELETE SET NULL
                        )
                    """))
                    conn.execute(text("""
                        INSERT INTO devin_sessions_new 
                        SELECT * FROM devin_sessions
                    """))
                    conn.execute(text("DROP TABLE devin_sessions"))
                    conn.execute(text("ALTER TABLE devin_sessions_new RENAME TO devin_sessions"))
                    conn.execute(text("CREATE INDEX ix_devin_sessions_removal_request_id ON devin_sessions(removal_request_id)"))
                    conn.execute(text("CREATE INDEX ix_devin_sessions_devin_session_id ON devin_sessions(devin_session_id)"))
                    conn.execute(text("CREATE INDEX ix_devin_sessions_status ON devin_sessions(status)"))
                    conn.execute(text("PRAGMA foreign_keys=ON"))
                    conn.commit()
                    logger.info("Successfully migrated devin_sessions table")
        except Exception as e:
            logger.warning(f"Migration for devin_sessions.removal_request_id failed: {e}")
    
    logger.info("Database initialized")


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CreateRemovalRequest(BaseModel):
    """Request body for creating a new removal request."""
    
    flag_key: str = Field(..., min_length=1, description="Feature flag key to remove")
    repositories: List[str] = Field(default=[], description="List of repository URLs (legacy)")
    repository_id: Optional[int] = Field(None, description="Repository ID (new flow)")
    feature_flag_provider: Optional[str] = Field(None, description="Feature flag provider name")
    preserve_mode: Literal['enabled', 'disabled'] = Field('enabled', description="Which code path to preserve")
    created_by: str = Field(..., min_length=1, description="User email or identifier")
    
    @validator('flag_key')
    def validate_flag_key(cls, v):
        """Validate flag key is not empty."""
        if not v or not v.strip():
            raise ValueError("Flag key cannot be empty")
        return v.strip()
    
    @model_validator(mode='after')
    def validate_repo_source(self):
        """Validate that either repository_id or repositories is provided."""
        repository_id = self.repository_id
        repositories = self.repositories
        
        if not repository_id and not repositories:
            raise ValueError("Either repository_id or repositories list is required")
        
        if repository_id and repositories:
            raise ValueError("Provide either repository_id or repositories list, not both")
        
        if repositories and len(repositories) > 5:
            raise ValueError("Maximum 5 repositories per request")
        
        for repo in repositories:
            if not repo.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid repository URL: {repo}")
        
        return self


class APIModel(BaseModel):
    """Base model for API responses with common config."""
    model_config = ConfigDict(from_attributes=True)


class SessionResponse(APIModel):
    """Response model for a Devin session."""
    id: int
    repository: str
    devin_session_id: Optional[str]
    devin_session_url: Optional[str]
    status: str
    pr_url: Optional[str]
    structured_output: Optional[Dict[str, Any]]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    acu_consumed: Optional[int]


class RemovalRequestResponse(APIModel):
    """Response model for a removal request."""
    id: int
    flag_key: str
    repositories: List[str]
    feature_flag_provider: Optional[str]
    preserve_mode: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]
    total_acu_consumed: int
    sessions: List[SessionResponse] = []


class RemovalRequestListItem(APIModel):
    """Simplified response model for list view."""
    id: int
    flag_key: str
    repositories: List[str]
    feature_flag_provider: Optional[str]
    preserve_mode: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    session_count: int
    completed_sessions: int
    failed_sessions: int
    total_acu_consumed: int = 0


class RemovalRequestListResponse(BaseModel):
    """Response model for list of removal requests with pagination."""
    total: int
    limit: int
    offset: int
    results: List[RemovalRequestListItem]


class SessionLogResponse(APIModel):
    """Response model for a session log entry."""
    id: int
    devin_session_id: int
    timestamp: datetime
    log_level: str
    message: str
    event_type: Optional[str]


class LogsResponse(BaseModel):
    """Response model for logs endpoint."""
    removal_request_id: int
    logs: List[SessionLogResponse]


class CreateRepository(BaseModel):
    """Request body for creating a new repository."""
    url: str = Field(..., min_length=1, description="Repository URL")
    github_token: Optional[str] = Field(None, description="GitHub token for private repos")
    
    @validator('url')
    def validate_url(cls, v):
        """Validate repository URL."""
        if not v or not v.strip():
            raise ValueError("Repository URL cannot be empty")
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid repository URL: {v}")
        return v


class CurrentScan(APIModel):
    """Response model for an active scan."""
    status: str
    devin_session_id: str
    devin_session_url: str
    started_at: Optional[str] = None


class RepositoryResponse(APIModel):
    """Response model for a repository."""
    id: int
    url: str
    provider_detected: Optional[str]
    last_scanned_at: Optional[datetime]
    created_at: datetime
    flag_count: int = 0
    current_scan: Optional[CurrentScan] = None


class DiscoveredFlagResponse(APIModel):
    """Response model for a discovered flag."""
    id: int
    repository_id: int
    flag_key: str
    occurrences: int
    files: List[str] = []
    provider: Optional[str]
    last_seen_at: datetime
    repository_url: Optional[str] = None


class SessionStatus(Enum):
    """Devin session status values"""
    WORKING = "working"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    FINISHED = "finished"


@dataclass
class DevinSessionResponse:
    """Response from creating a Devin session"""
    session_id: str
    url: str
    is_new_session: Optional[bool] = None


@dataclass
class DevinSessionDetails:
    """Detailed information about a Devin session"""
    session_id: str
    status: str
    status_enum: Optional[str]
    title: Optional[str]
    created_at: str
    updated_at: str
    pull_request: Optional[Dict[str, str]]
    structured_output: Optional[Dict[str, Any]]


class DevinAPIClient:
    """Client for interacting with the Devin AI API."""
    
    BASE_URL = "https://api.devin.ai/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEVIN_API_KEY")
        if not self.api_key:
            raise ValueError("API key required. Set DEVIN_API_KEY env var.")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def create_session(
        self,
        prompt: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        idempotent: Optional[bool] = True
    ) -> DevinSessionResponse:
        """Create a new Devin session."""
        payload = {"prompt": prompt}
        
        if title is not None:
            payload["title"] = title
        if tags is not None:
            payload["tags"] = tags
        if idempotent is not None:
            payload["idempotent"] = idempotent
        
        response = requests.post(
            f"{self.BASE_URL}/sessions",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        return DevinSessionResponse(
            session_id=data["session_id"],
            url=data["url"],
            is_new_session=data.get("is_new_session")
        )
    
    def get_session_details(self, session_id: str) -> DevinSessionDetails:
        """Retrieve detailed information about a session."""
        response = requests.get(
            f"{self.BASE_URL}/sessions/{session_id}",
            headers=self.headers
        )
        response.raise_for_status()
        
        data = response.json()
        return DevinSessionDetails(
            session_id=data["session_id"],
            status=data["status"],
            status_enum=data.get("status_enum"),
            title=data.get("title"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            pull_request=data.get("pull_request"),
            structured_output=data.get("structured_output")
        )


class SessionMonitor:
    """Monitors active Devin sessions and updates database with latest status."""
    
    def __init__(self, devin_client: DevinAPIClient):
        self.devin_client = devin_client
        self.poll_interval = POLL_INTERVAL
        self.running = True
    
    async def start(self):
        """Main monitoring loop."""
        logger.info("SessionMonitor started")
        
        while self.running:
            try:
                await self.poll_active_sessions()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
    
    async def poll_active_sessions(self):
        """Poll all active Devin sessions for status updates."""
        db = SessionLocal()
        try:
            active_sessions = db.query(DevinSession).filter(
                DevinSession.status.in_(['pending', 'claimed', 'working', 'blocked'])
            ).all()
            
            logger.debug(f"Polling {len(active_sessions)} active sessions")
            
            for session in active_sessions:
                try:
                    if not session.devin_session_id:
                        continue
                    
                    details = self.devin_client.get_session_details(session.devin_session_id)
                    
                    old_status = session.status
                    await self.update_session_status(db, session, details)
                    
                    if old_status != session.status:
                        await self.log_status_change(db, session, details)
                    
                    await self.update_removal_request_status(db, session.removal_request_id)
                    
                    if details.status_enum in ['finished', 'expired']:
                        await self.handle_completion(db, session, details)
                    
                    await self.check_timeout(db, session)
                    
                except Exception as e:
                    logger.error(f"Error polling session {session.id}: {e}", exc_info=True)
                    await self.handle_poll_error(db, session, e)
            
            db.commit()
        except Exception as e:
            logger.error(f"Error in poll_active_sessions: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    async def update_session_status(self, db: Session, session: DevinSession, details):
        """Update session status in database."""
        status = details.status_enum or details.status
        if status:
            session.status = status.lower() if isinstance(status, str) else status
        
        if details.pull_request:
            session.pr_url = details.pull_request.get('url')
        
        if details.structured_output:
            session.structured_output = json.dumps(details.structured_output)
            
            if isinstance(details.structured_output, dict):
                acu = self._extract_acu_from_output(details.structured_output)
                if acu is not None:
                    session.acu_consumed = acu
        
        if details.status_enum in ['finished', 'expired'] and not session.completed_at:
            session.completed_at = datetime.utcnow()
        
        db.add(session)
    
    def _extract_acu_from_output(self, output: Dict[str, Any]) -> Optional[int]:
        """Extract ACU consumed from structured output, trying multiple common locations."""
        if not isinstance(output, dict):
            return None
        
        acu_keys = ['acu_consumed', 'acu', 'agent_credits', 'credits']
        for key in acu_keys:
            if key in output and output[key] is not None:
                try:
                    return int(output[key])
                except (ValueError, TypeError):
                    continue
        
        if 'usage' in output and isinstance(output['usage'], dict):
            for key in acu_keys:
                if key in output['usage'] and output['usage'][key] is not None:
                    try:
                        return int(output['usage'][key])
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    async def log_status_change(self, db: Session, session: DevinSession, details):
        """Log status change event."""
        log_entry = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level='info',
            message=f"Status changed to: {details.status_enum}",
            event_type='status_change'
        )
        db.add(log_entry)
    
    async def handle_completion(self, db: Session, session: DevinSession, details):
        """Handle session completion."""
        logger.info(f"Session {session.id} completed with status: {details.status_enum}")
        
        log_entry = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level='info',
            message=f"Session completed: {details.status_enum}",
            event_type='completion'
        )
        db.add(log_entry)
        
        if not session.removal_request_id and details.structured_output:
            if isinstance(details.structured_output, dict) and 'flags' in details.structured_output and 'provider' in details.structured_output:
                logger.info(f"Detected discovery session completion for {session.repository}")
                await self.persist_discovery_results(db, session.repository, details.structured_output)
        
        await self.update_removal_request_status(db, session.removal_request_id)
    
    async def check_timeout(self, db: Session, session: DevinSession):
        """Check if session has exceeded timeout threshold."""
        if not session.started_at:
            return
        
        elapsed = (datetime.utcnow() - session.started_at).total_seconds()
        
        if elapsed > TIMEOUT_THRESHOLD and session.status == 'working':
            logger.warning(f"Session {session.id} exceeded timeout threshold")
            await self.handle_timeout(db, session)
    
    async def handle_timeout(self, db: Session, session: DevinSession):
        """Handle session timeout."""
        session.status = 'expired'
        session.error_message = 'Session timed out after 15 minutes'
        session.completed_at = datetime.utcnow()
        db.add(session)
        
        log_entry = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level='error',
            message='Session timed out after 15 minutes',
            event_type='timeout'
        )
        db.add(log_entry)
        
        await self.update_removal_request_status(db, session.removal_request_id)
    
    async def handle_poll_error(self, db: Session, session: DevinSession, error: Exception):
        """Handle error during polling."""
        log_entry = SessionLog(
            devin_session_id=session.id,
            timestamp=datetime.utcnow(),
            log_level='error',
            message=f"Error polling session: {str(error)}",
            event_type='error'
        )
        db.add(log_entry)
    
    async def persist_discovery_results(self, db: Session, repository_url: str, structured_output: dict):
        """Persist discovery scan results to database."""
        try:
            repository = db.query(Repository).filter_by(url=repository_url).first()
            if not repository:
                logger.warning(f"Repository not found for URL: {repository_url}")
                return
            
            provider = structured_output.get('provider') or 'Unknown'
            repository.provider_detected = provider
            repository.last_scanned_at = datetime.utcnow()
            db.add(repository)
            
            db.query(DiscoveredFlag).filter_by(repository_id=repository.id).delete()
            
            flags = structured_output.get('flags', [])
            for flag_data in flags:
                if not isinstance(flag_data, dict):
                    continue
                
                flag = DiscoveredFlag(
                    repository_id=repository.id,
                    flag_key=flag_data.get('key', ''),
                    occurrences=int(flag_data.get('occurrences', 0)),
                    files=json.dumps(flag_data.get('files', [])),
                    provider=provider,
                    last_seen_at=datetime.utcnow()
                )
                db.add(flag)
            
            logger.info(f"Persisted {len(flags)} flags for repository {repository.id}")
            
        except Exception as e:
            logger.error(f"Error persisting discovery results: {e}", exc_info=True)
    
    async def update_removal_request_status(self, db: Session, removal_request_id: int):
        """Update removal request status based on session statuses."""
        if not removal_request_id:
            return
        
        removal_request = db.query(RemovalRequest).filter_by(id=removal_request_id).first()
        if not removal_request:
            return
        
        sessions = removal_request.sessions
        
        if all(s.status in ['finished', 'expired'] for s in sessions):
            if any(s.status == 'expired' or s.error_message for s in sessions):
                removal_request.status = 'failed'
            else:
                removal_request.status = 'completed'
        elif any(s.status in ['claimed', 'working', 'blocked'] for s in sessions):
            removal_request.status = 'in_progress'
        else:
            removal_request.status = 'queued'
        
        total_acu = sum(s.acu_consumed or 0 for s in sessions)
        removal_request.total_acu_consumed = total_acu
        
        removal_request.updated_at = datetime.utcnow()
        db.add(removal_request)
    
    def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        logger.info("SessionMonitor stopped")


class SessionQueue:
    """Queue for managing Devin session creation with concurrency limits."""
    
    def __init__(self, devin_client: DevinAPIClient, max_concurrent: int = MAX_CONCURRENT_SESSIONS):
        self.devin_client = devin_client
        self.max_concurrent = max_concurrent
        self.running = True
    
    async def start(self):
        """Process queue continuously."""
        logger.info("SessionQueue started")
        
        while self.running:
            try:
                db = SessionLocal()
                try:
                    active_count = self.get_active_count(db)
                    
                    if active_count < self.max_concurrent:
                        session = db.query(DevinSession).filter_by(
                            status='pending'
                        ).order_by(DevinSession.id).first()
                        
                        if session:
                            await self.start_session(db, session)
                            db.commit()
                    
                    await asyncio.sleep(5)  # Check every 5 seconds
                except Exception as e:
                    logger.error(f"Queue error: {e}", exc_info=True)
                    db.rollback()
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Queue loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def start_session(self, db: Session, session: DevinSession):
        """Start a Devin session."""
        try:
            removal_request = session.removal_request
            
            prompt = self.build_removal_prompt(
                flag_key=removal_request.flag_key,
                repository=session.repository,
                provider=removal_request.feature_flag_provider,
                preserve_mode=removal_request.preserve_mode
            )
            
            logger.info(f"Creating Devin session for removal request {removal_request.id}, repository {session.repository}")
            
            devin_session = self.devin_client.create_session(
                prompt=prompt,
                title=f"Remove flag: {removal_request.flag_key}",
                tags=["flag-removal", removal_request.flag_key, f"preserve:{removal_request.preserve_mode}"],
                idempotent=True
            )
            
            session.devin_session_id = devin_session.session_id
            session.devin_session_url = devin_session.url
            session.status = 'claimed'
            session.started_at = datetime.utcnow()
            db.add(session)
            
            log_entry = SessionLog(
                devin_session_id=session.id,
                timestamp=datetime.utcnow(),
                log_level='info',
                message=f"Devin session created: {devin_session.session_id}",
                event_type='session_created'
            )
            db.add(log_entry)
            
            logger.info(f"Started session {session.id}: {devin_session.session_id}")
            
            removal_request = session.removal_request
            if removal_request.status == 'queued':
                removal_request.status = 'in_progress'
                removal_request.updated_at = datetime.utcnow()
                db.add(removal_request)
            
        except Exception as e:
            logger.error(f"Failed to start session {session.id}: {e}", exc_info=True)
            session.status = 'failed'
            session.error_message = str(e)
            db.add(session)
            
            log_entry = SessionLog(
                devin_session_id=session.id,
                timestamp=datetime.utcnow(),
                log_level='error',
                message=f"Failed to create Devin session: {str(e)}",
                event_type='error'
            )
            db.add(log_entry)
    
    def build_removal_prompt(self, flag_key: str, repository: str, provider: Optional[str], preserve_mode: str = 'enabled') -> str:
        """Build the prompt for Devin to remove a feature flag."""
        preserve_instruction = f'Preserve the "{preserve_mode}" code path and remove the "{("disabled" if preserve_mode == "enabled" else "enabled")}" code path.'
        
        prompt = f"""Task: Remove feature flag from codebase

Flag Key: {flag_key}
Repository: {repository}
Provider: {provider or 'Unknown'}

BEFORE YOU START:
1. Clone the repository
2. Search the ENTIRE codebase for ALL variations of this flag:
   - Exact match: "{flag_key}"
   - camelCase version (if applicable)
   - kebab-case version (if applicable)
   - SCREAMING_SNAKE_CASE version
   - Partial matches (last 2-3 words of the flag name)
   
   Example: For flag "enable_new_checkout", search for:
   - enable_new_checkout (exact)
   - enableNewCheckout (camelCase)
   - enable-new-checkout (kebab-case)
   - ENABLE_NEW_CHECKOUT (SCREAMING_SNAKE_CASE)
   - new_checkout (partial)

3. Search in ALL file types across the entire repository (including but not limited to: source code, tests, documentation, config files, CI/CD configs, build files, environment files, etc.)
4. Use comprehensive search commands like: grep -r, git grep, or IDE-wide search to ensure nothing is missed
5. Document your initial findings: "Found X total occurrences across Y files"

EDGE CASES TO WATCH FOR:
- Flag in database migrations (DO NOT remove - note in warnings)
- Flag in environment variable files (.env, .env.example) - list in warnings for manual review
- Flag in third-party library code (DO NOT modify - note in warnings)
- Flag in archived/deprecated code sections - use judgment and note in warnings

REMOVAL STRATEGY:
1. Determine if this flag ENABLES or DISABLES a feature when set to true
2. Based on preserve mode "{preserve_mode}":
   - If "enabled": Keep the code that runs when flag is TRUE, remove the FALSE path
   - If "disabled": Keep the code that runs when flag is FALSE, remove the TRUE path
3. NEVER set boolean values to 'undefined'
   - Use explicit true/false values, OR
   - Remove the property/variable entirely if it's no longer needed
4. {preserve_instruction}
5. Remove the flag check itself along with the unwanted code path

REMOVAL STEPS:
1. Remove flag definition from feature flag registry/constants
2. Remove flag from default values/configuration
3. Remove conditional checks and simplify to single code path
4. Remove flag references from tests
5. Remove flag from documentation
6. Clean up any imports that are no longer needed

VERIFICATION (CRITICAL):
1. After removal, search the codebase again for "{flag_key}"
2. Run the project's test suite:
   - npm test / yarn test (for Node.js)
   - pytest / python -m pytest (for Python)
   - ./gradlew test (for Java)
   - Whatever is appropriate for this repo
3. Document test results with actual output
4. If tests fail, investigate and fix. If you cannot fix within 3 attempts, STOP and document:
   - What tests are failing
   - Why they're failing
   - What you tried to fix them
   - Set pr_url to null and explain in warnings
5. Count final occurrences - should be ZERO

ROLLBACK/STOP CONDITIONS:
If you realize mid-way that you cannot complete this safely:
- Document what you've discovered and why it's unsafe
- List specific concerns or blockers
- Set pr_url to null
- Provide detailed explanation in warnings array
- Do NOT create a partial/incomplete PR

CREATE PULL REQUEST:
- Title: "[Devin-Automated] Remove feature flag: {flag_key}"
- Description: Write a comprehensive story of the removal process:
  1. Initial search results: "Cloned repository {repository}, found X total occurrences across Y files"
  2. List all file types where flag was found (e.g., "Found in: TypeScript files, test files, JSON configs")
  3. Partial match handling: If you found variations (camelCase, kebab-case, etc.), list them
  4. Detailed changes: For each file modified, explain what was replaced (e.g., "In src/utils.ts: Replaced conditional check with '{preserve_mode}' path, removed 3 occurrences")
  5. Code path decision: "Preserved '{preserve_mode}' code path and removed '{("disabled" if preserve_mode == "enabled" else "enabled")}' path"
  6. Build/compile verification: "Ran build/compile checks to ensure syntax correctness: [result]"
  7. Test execution: "Ran test suite: [command] - [results with pass/fail counts]"
  8. Final verification: "Re-searched codebase for '{flag_key}' - X references remaining (should be 0)"
  9. Any warnings or concerns that require human review
- Label: "feature-flag-removal"
- CRITICAL: Do NOT add any new .txt or .md documentation files to the PR
- CRITICAL: Do NOT create summary files, changelog files, or documentation updates
- Only commit actual code changes (source files, tests, configs that existed before)

Important:
- Do NOT remove code that is still needed
- Run all tests before creating PR
- If tests fail, investigate and fix
- If you need clarification, ask before proceeding
- If you encounter ambiguity about which code path to preserve, STOP and ask for clarification
- If you cannot create a PR, set pr_url to null and explain in warnings
- If references_remaining > 0, list the files in warnings

IMPORTANT: Return structured output as a JSON object with these keys and types:
- references_found_initially: integer (total occurrences found in initial search)
- references_removed: integer (count of flag occurrences you removed)
- references_remaining: integer (should be 0 after complete removal)
- files_modified: array of strings (paths to files you changed)
- pr_url: string (the GitHub PR URL you created, or null if unable to create)
- test_command_run: string (actual test command executed, or "not run")
- test_results: string (e.g., "PASSED: 45 tests" or "FAILED: reason" or "SKIPPED")
- code_path_preserved: string (one of: "enabled" or "disabled")
- warnings: array of strings (any issues, ambiguities, or items needing manual review)
- acu_consumed: integer (actual ACU credits used for this session)
- verification_search_output: string (output from final search command to verify removal)

Populate all values using the actual results of your work. Do not use placeholder or example values.
"""
        return prompt
    
    def build_discovery_prompt(self, repository: str, github_token: Optional[str] = None) -> str:
        """Build the prompt for Devin to discover feature flags in a repository."""
        token_instruction = f"\nGitHub Token: {github_token}" if github_token else "\nNote: This is a public repository, no token needed."
        
        prompt = f"""Task: Discover all feature flags in codebase

Repository: {repository}{token_instruction}

OBJECTIVE:
Scan the entire repository to identify ALL feature flags and their usage patterns. This is a READ-ONLY task - do NOT modify any files or create PRs.

STEP 1: DETECT PROVIDER
Identify which feature flag provider(s) are used by searching for:
- LaunchDarkly: imports/requires of 'launchdarkly', 'ld-client', configuration files
- Statsig: imports of 'statsig', configuration files
- Unleash: imports of 'unleash-client', configuration files
- Split.io: imports of 'splitio', configuration files
- Custom: Look for internal flag management systems, environment variables, config files

STEP 2: COMPREHENSIVE FLAG SEARCH
Search the ENTIRE codebase for flag usage patterns:

For LaunchDarkly:
- variation(), boolVariation(), stringVariation(), etc.
- Look for flag keys as strings in these calls

For Statsig:
- checkGate(), getExperiment(), getConfig()
- Look for gate/experiment names

For Unleash:
- isEnabled(), getVariant()
- Look for toggle names

For Custom/Environment:
- process.env.FEATURE_*, process.env.ENABLE_*
- Config object properties
- Boolean flags in settings files

STEP 3: CATALOG EACH FLAG
For each unique flag found, record:
- Flag key/name (exact string)
- Number of occurrences in codebase
- List of files where it appears (full paths)
- Which provider it belongs to

STEP 4: SEARCH COMPREHENSIVELY
Use multiple search strategies:
- grep -r for flag provider API calls
- Search config files (.json, .yaml, .env, .env.example)
- Search source code (all languages)
- Search test files
- Search documentation

IMPORTANT: Return structured output as a JSON object with these keys:
- provider: string (detected provider: "LaunchDarkly", "Statsig", "Unleash", "Split.io", "Custom", or "Multiple")
- flags: array of objects, each with:
  - key: string (flag name/key)
  - occurrences: integer (total count in codebase)
  - files: array of strings (file paths where flag appears)
- total_flags: integer (unique flag count)
- total_occurrences: integer (sum of all occurrences)
- warnings: array of strings (any issues or ambiguities encountered)
- acu_consumed: integer (actual ACU credits used)

CRITICAL INSTRUCTIONS:
- Do NOT modify any files
- Do NOT create any PRs
- Do NOT create any documentation files
- This is a READ-ONLY discovery task
- Populate all values using actual search results
- Do not use placeholder or example values
- If you cannot determine the provider, set it to "Unknown"
- If no flags are found, return empty flags array with total_flags: 0
"""
        return prompt
    
    def get_active_count(self, db: Session) -> int:
        """Get count of active Devin sessions."""
        return db.query(DevinSession).filter(
            DevinSession.status.in_(['pending', 'claimed', 'working', 'blocked'])
        ).count()
    
    def stop(self):
        """Stop the queue processing."""
        self.running = False
        logger.info("SessionQueue stopped")


app = FastAPI(
    title="Feature Flag Removal Orchestration API",
    description="Lightweight API for orchestrating feature flag removal using Devin AI",
    version="2.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

monitor_task = None
queue_task = None
devin_client = None
session_queue = None


@app.on_event("startup")
async def startup_event():
    """Initialize database and start background services."""
    global monitor_task, queue_task, devin_client, session_queue
    
    logger.info("Starting up application...")
    
    init_db()
    logger.info("Database initialized")
    
    api_key = os.getenv("DEVIN_API_KEY")
    if not api_key:
        logger.warning("DEVIN_API_KEY not set - background services will not start")
        return
    
    devin_client = DevinAPIClient(api_key=api_key)
    logger.info("Devin API client initialized")
    
    monitor = SessionMonitor(devin_client)
    session_queue = SessionQueue(devin_client, max_concurrent=MAX_CONCURRENT_SESSIONS)
    
    monitor_task = asyncio.create_task(monitor.start())
    queue_task = asyncio.create_task(session_queue.start())
    
    logger.info("Background services started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background services."""
    logger.info("Shutting down application...")
    
    if monitor_task:
        monitor_task.cancel()
    if queue_task:
        queue_task.cancel()
    
    logger.info("Background services stopped")


@app.get("/")
async def root():
    """Serve the frontend application."""
    frontend_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"message": "Frontend not found. API is running at /api/"}


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/removals", response_model=RemovalRequestResponse, status_code=201)
async def create_removal(
    body: CreateRemovalRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new feature flag removal request.
    
    This will create Devin sessions for each repository.
    Supports both legacy (repositories list) and new (repository_id) flows.
    """
    try:
        active_count = db.query(DevinSession).filter(
            DevinSession.status.in_(['pending', 'claimed', 'working', 'blocked'])
        ).count()
        
        if active_count >= MAX_CONCURRENT_SESSIONS:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "System at capacity",
                    "active_sessions": active_count,
                    "max_sessions": MAX_CONCURRENT_SESSIONS,
                    "retry_after": 300
                }
            )
        
        repos_to_process = []
        provider = body.feature_flag_provider
        
        if body.repository_id:
            repository = db.query(Repository).filter_by(id=body.repository_id).first()
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")
            
            repos_to_process = [repository.url]
            if not provider and repository.provider_detected:
                provider = repository.provider_detected
        else:
            if len(body.repositories) > MAX_REPOS_PER_REQUEST:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum {MAX_REPOS_PER_REQUEST} repositories per request"
                )
            repos_to_process = body.repositories
        
        removal_request = RemovalRequest(
            flag_key=body.flag_key,
            repositories=json.dumps(repos_to_process),
            repository_id=body.repository_id,
            feature_flag_provider=provider,
            preserve_mode=body.preserve_mode,
            status='queued',
            created_by=body.created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(removal_request)
        db.flush()
        
        for repo in repos_to_process:
            session = DevinSession(
                removal_request_id=removal_request.id,
                repository=repo,
                status='pending',
                devin_session_id=None,
                devin_session_url=None
            )
            db.add(session)
        
        db.commit()
        db.refresh(removal_request)
        
        logger.info(f"Created removal request {removal_request.id} for flag {body.flag_key}")
        
        return _build_removal_response(removal_request)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating removal request: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/removals", response_model=RemovalRequestListResponse)
async def list_removals(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List all removal requests with optional filtering and pagination.
    
    Query parameters:
    - status: Filter by status (queued, in_progress, completed, failed)
    - limit: Number of results to return (default: 50, max: 100)
    - offset: Number of results to skip (default: 0)
    """
    try:
        if limit > 100:
            limit = 100
        
        query = db.query(RemovalRequest)
        
        if status:
            query = query.filter(RemovalRequest.status == status)
        
        total = query.count()
        
        requests = query.order_by(RemovalRequest.created_at.desc()).offset(offset).limit(limit).all()
        
        results = []
        for req in requests:
            sessions = req.sessions
            results.append(RemovalRequestListItem(
                id=req.id,
                flag_key=req.flag_key,
                repositories=json.loads(req.repositories),
                feature_flag_provider=req.feature_flag_provider,
                preserve_mode=req.preserve_mode,
                status=req.status,
                created_by=req.created_by,
                created_at=req.created_at,
                updated_at=req.updated_at,
                session_count=len(sessions),
                completed_sessions=sum(1 for s in sessions if s.status in ['finished', 'expired']),
                failed_sessions=sum(1 for s in sessions if s.error_message or s.status == 'expired'),
                total_acu_consumed=req.total_acu_consumed
            ))
        
        return RemovalRequestListResponse(
            total=total,
            limit=limit,
            offset=offset,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error listing removal requests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/removals/{id}", response_model=RemovalRequestResponse)
async def get_removal(id: int, db: Session = Depends(get_db)):
    """
    Get details of a specific removal request including all sessions.
    """
    try:
        removal_request = db.query(RemovalRequest).filter_by(id=id).first()
        
        if not removal_request:
            raise HTTPException(status_code=404, detail="Removal request not found")
        
        return _build_removal_response(removal_request)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting removal request {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/removals/{id}/logs", response_model=LogsResponse)
async def get_removal_logs(id: int, db: Session = Depends(get_db)):
    """
    Get all logs for a removal request across all sessions.
    """
    try:
        removal_request = db.query(RemovalRequest).filter_by(id=id).first()
        
        if not removal_request:
            raise HTTPException(status_code=404, detail="Removal request not found")
        
        logs = []
        for session in removal_request.sessions:
            session_logs = db.query(SessionLog).filter_by(
                devin_session_id=session.id
            ).order_by(SessionLog.timestamp.asc()).all()
            logs.extend(session_logs)
        
        logs.sort(key=lambda x: x.timestamp)
        
        return LogsResponse(
            removal_request_id=id,
            logs=[SessionLogResponse.from_orm(log) for log in logs]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting logs for removal request {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories", response_model=RepositoryResponse, status_code=201)
async def create_repository(
    body: CreateRepository,
    db: Session = Depends(get_db)
):
    """Create a new repository and optionally trigger initial scan."""
    try:
        existing = db.query(Repository).filter_by(url=body.url).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Repository already exists with id {existing.id}"
            )
        
        repository = Repository(
            url=body.url,
            github_token=body.github_token,
            created_at=datetime.utcnow()
        )
        db.add(repository)
        db.commit()
        db.refresh(repository)
        
        logger.info(f"Created repository {repository.id}: {repository.url}")
        
        return RepositoryResponse(
            id=repository.id,
            url=repository.url,
            provider_detected=repository.provider_detected,
            last_scanned_at=repository.last_scanned_at,
            created_at=repository.created_at,
            flag_count=0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating repository: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories", response_model=List[RepositoryResponse])
async def list_repositories(db: Session = Depends(get_db)):
    """List all registered repositories with flag counts."""
    try:
        repositories = db.query(Repository).order_by(Repository.created_at.desc()).all()
        
        results = []
        for repo in repositories:
            flag_count = db.query(DiscoveredFlag).filter_by(repository_id=repo.id).count()
            
            current_scan = None
            active_session = db.query(DevinSession).filter(
                DevinSession.removal_request_id.is_(None),
                DevinSession.repository == repo.url,
                DevinSession.status.notin_(['finished', 'failed', 'expired'])
            ).order_by(DevinSession.started_at.desc()).first()
            
            if active_session:
                current_scan = {
                    'status': active_session.status,
                    'devin_session_id': active_session.devin_session_id,
                    'devin_session_url': active_session.devin_session_url,
                    'started_at': active_session.started_at.isoformat() if active_session.started_at else None
                }
            
            results.append(RepositoryResponse(
                id=repo.id,
                url=repo.url,
                provider_detected=repo.provider_detected,
                last_scanned_at=repo.last_scanned_at,
                created_at=repo.created_at,
                flag_count=flag_count,
                current_scan=current_scan
            ))
        
        return results
        
    except Exception as e:
        logger.error(f"Error listing repositories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repositories/{id}", response_model=RepositoryResponse)
async def get_repository(id: int, db: Session = Depends(get_db)):
    """Get details of a specific repository."""
    try:
        repository = db.query(Repository).filter_by(id=id).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        flag_count = db.query(DiscoveredFlag).filter_by(repository_id=repository.id).count()
        
        current_scan = None
        active_session = db.query(DevinSession).filter(
            DevinSession.removal_request_id.is_(None),
            DevinSession.repository == repository.url,
            DevinSession.status.notin_(['finished', 'failed', 'expired'])
        ).order_by(DevinSession.started_at.desc()).first()
        
        if active_session:
            current_scan = {
                'status': active_session.status,
                'devin_session_id': active_session.devin_session_id,
                'devin_session_url': active_session.devin_session_url,
                'started_at': active_session.started_at.isoformat() if active_session.started_at else None
            }
        
        return RepositoryResponse(
            id=repository.id,
            url=repository.url,
            provider_detected=repository.provider_detected,
            last_scanned_at=repository.last_scanned_at,
            created_at=repository.created_at,
            flag_count=flag_count,
            current_scan=current_scan
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting repository {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/repositories/{id}", status_code=204)
async def delete_repository(id: int, db: Session = Depends(get_db)):
    """Delete a repository and all associated discovered flags."""
    try:
        repository = db.query(Repository).filter_by(id=id).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        db.delete(repository)
        db.commit()
        
        logger.info(f"Deleted repository {id}: {repository.url}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting repository {id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


def _format_flag_response(flag: DiscoveredFlag, repository_url: Optional[str] = None) -> DiscoveredFlagResponse:
    """Helper to format a DiscoveredFlag as a response object."""
    files = []
    if flag.files:
        try:
            files = json.loads(flag.files)
        except:
            pass
    
    if repository_url is None and flag.repository:
        repository_url = flag.repository.url
    
    return DiscoveredFlagResponse(
        id=flag.id,
        repository_id=flag.repository_id,
        flag_key=flag.flag_key,
        occurrences=flag.occurrences,
        files=files,
        provider=flag.provider,
        last_seen_at=flag.last_seen_at,
        repository_url=repository_url
    )


@app.get("/api/repositories/{id}/flags", response_model=List[DiscoveredFlagResponse])
async def get_repository_flags(id: int, db: Session = Depends(get_db)):
    """Get all discovered flags for a specific repository."""
    try:
        repository = db.query(Repository).filter_by(id=id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        flags = db.query(DiscoveredFlag).filter_by(repository_id=id).order_by(
            DiscoveredFlag.last_seen_at.desc()
        ).all()
        
        return [_format_flag_response(flag, repository.url) for flag in flags]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flags for repository {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/flags", response_model=List[DiscoveredFlagResponse])
async def list_flags(
    repository_id: Optional[int] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all discovered flags with optional filters."""
    try:
        query = db.query(DiscoveredFlag)
        
        if repository_id:
            query = query.filter(DiscoveredFlag.repository_id == repository_id)
        
        if provider:
            query = query.filter(DiscoveredFlag.provider == provider)
        
        flags = query.order_by(DiscoveredFlag.last_seen_at.desc()).all()
        return [_format_flag_response(flag) for flag in flags]
        
    except Exception as e:
        logger.error(f"Error listing flags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/repositories/{id}/scan", status_code=202)
async def scan_repository(id: int, db: Session = Depends(get_db)):
    """Trigger a flag discovery scan for a repository."""
    try:
        if devin_client is None:
            raise HTTPException(status_code=503, detail="Devin services not initialized - DEVIN_API_KEY may be missing")
        
        repository = db.query(Repository).filter_by(id=id).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        if session_queue is None:
            prompt = SessionQueue(devin_client).build_discovery_prompt(
                repository=repository.url,
                github_token=repository.github_token
            )
        else:
            prompt = session_queue.build_discovery_prompt(
                repository=repository.url,
                github_token=repository.github_token
            )
        
        logger.info(f"Starting discovery scan for repository {id}: {repository.url}")
        
        devin_session = devin_client.create_session(
            prompt=prompt,
            title=f"Discover flags: {repository.url}",
            tags=["discovery", f"repo:{id}"],
            idempotent=True
        )
        
        logger.info(f"Created discovery session {devin_session.session_id} for repository {id}")
        
        session = DevinSession(
            removal_request_id=None,  # Discovery sessions aren't linked to removal requests
            repository=repository.url,
            status='claimed',
            devin_session_id=devin_session.session_id,
            devin_session_url=devin_session.url,
            started_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        
        return {
            "message": "Scan started",
            "repository_id": id,
            "devin_session_id": devin_session.session_id,
            "devin_session_url": devin_session.url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting scan for repository {id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/removals/{id}/stream")
async def stream_removal_status(id: int, db: Session = Depends(get_db)):
    """
    Stream real-time status updates for a removal request using Server-Sent Events.
    
    The client will receive events:
    - status_update: When the status changes
    - heartbeat: Every 30 seconds to keep connection alive
    - complete: When the removal request is complete
    - error: If an error occurs
    """
    removal_request = db.query(RemovalRequest).filter_by(id=id).first()
    if not removal_request:
        raise HTTPException(status_code=404, detail="Removal request not found")
    
    async def event_generator():
        last_update = None
        heartbeat_counter = 0
        
        try:
            while True:
                db_local = next(get_db())
                
                try:
                    removal = db_local.query(RemovalRequest).filter_by(id=id).first()
                    
                    if not removal:
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": "Removal request not found"})
                        }
                        break
                    
                    sessions = removal.sessions
                    
                    status_data = {
                        "removal_id": removal.id,
                        "status": removal.status,
                        "updated_at": removal.updated_at.isoformat(),
                        "sessions": [
                            {
                                "id": s.id,
                                "repository": s.repository,
                                "status": s.status,
                                "pr_url": s.pr_url,
                                "error_message": s.error_message
                            }
                            for s in sessions
                        ]
                    }
                    
                    current_hash = hash(json.dumps(status_data, sort_keys=True))
                    if current_hash != last_update:
                        yield {
                            "event": "status_update",
                            "data": json.dumps(status_data)
                        }
                        last_update = current_hash
                    
                    heartbeat_counter += 1
                    if heartbeat_counter >= 6:
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({"timestamp": datetime.utcnow().isoformat()})
                        }
                        heartbeat_counter = 0
                    
                    if removal.status in ['completed', 'failed']:
                        yield {
                            "event": "complete",
                            "data": json.dumps({"status": removal.status})
                        }
                        break
                    
                finally:
                    db_local.close()
                
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for removal request {id}")
        except Exception as e:
            logger.error(f"Error in SSE stream for removal request {id}: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
    
    return EventSourceResponse(event_generator())


def _build_removal_response(removal_request: RemovalRequest) -> RemovalRequestResponse:
    """Helper to build RemovalRequestResponse from database model."""
    sessions = []
    for session in removal_request.sessions:
        structured_output = None
        if session.structured_output:
            try:
                structured_output = json.loads(session.structured_output)
            except:
                pass
        
        sessions.append(SessionResponse(
            id=session.id,
            repository=session.repository,
            devin_session_id=session.devin_session_id,
            devin_session_url=session.devin_session_url,
            status=session.status,
            pr_url=session.pr_url,
            structured_output=structured_output,
            started_at=session.started_at,
            completed_at=session.completed_at,
            error_message=session.error_message,
            acu_consumed=session.acu_consumed
        ))
    
    return RemovalRequestResponse(
        id=removal_request.id,
        flag_key=removal_request.flag_key,
        repositories=json.loads(removal_request.repositories),
        feature_flag_provider=removal_request.feature_flag_provider,
        preserve_mode=removal_request.preserve_mode,
        status=removal_request.status,
        created_by=removal_request.created_by,
        created_at=removal_request.created_at,
        updated_at=removal_request.updated_at,
        error_message=removal_request.error_message,
        total_acu_consumed=removal_request.total_acu_consumed,
        sessions=sessions
    )
