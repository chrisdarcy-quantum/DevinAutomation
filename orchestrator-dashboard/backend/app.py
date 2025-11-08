"""
Feature Flag Removal Orchestration Dashboard - Lightweight Backend
Single-file FastAPI application with all functionality consolidated.
"""

# ============================================================================
# ============================================================================

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import logging
import os
import time
import requests

# ============================================================================
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orchestrator.db")
MAX_REPOS_PER_REQUEST = 5
MAX_CONCURRENT_SESSIONS = 20
POLL_INTERVAL = 10  # seconds
TIMEOUT_THRESHOLD = 900  # 15 minutes in seconds

# ============================================================================
# ============================================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# ============================================================================

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

# ============================================================================
# ============================================================================

class CreateRemovalRequest(BaseModel):
    """Request body for creating a new removal request."""
    
    flag_key: str = Field(..., min_length=1, description="Feature flag key to remove")
    repositories: List[str] = Field(..., min_items=1, max_items=5, description="List of repository URLs")
    feature_flag_provider: Optional[str] = Field(None, description="Feature flag provider name")
    created_by: str = Field(..., min_length=1, description="User email or identifier")
    
    @validator('repositories')
    def validate_repositories(cls, v):
        """Validate repository URLs."""
        if not v:
            raise ValueError("At least one repository is required")
        if len(v) > 5:
            raise ValueError("Maximum 5 repositories per request")
        
        for repo in v:
            if not repo.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid repository URL: {repo}")
        
        return v
    
    @validator('flag_key')
    def validate_flag_key(cls, v):
        """Validate flag key is not empty."""
        if not v or not v.strip():
            raise ValueError("Flag key cannot be empty")
        return v.strip()


class SessionResponse(BaseModel):
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
    
    class Config:
        from_attributes = True


class RemovalRequestResponse(BaseModel):
    """Response model for a removal request."""
    
    id: int
    flag_key: str
    repositories: List[str]
    feature_flag_provider: Optional[str]
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]
    total_acu_consumed: int
    sessions: List[SessionResponse] = []
    
    class Config:
        from_attributes = True


class RemovalRequestListItem(BaseModel):
    """Simplified response model for list view."""
    
    id: int
    flag_key: str
    repositories: List[str]
    feature_flag_provider: Optional[str]
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    session_count: int
    completed_sessions: int
    failed_sessions: int
    
    class Config:
        from_attributes = True


class RemovalRequestListResponse(BaseModel):
    """Response model for list of removal requests with pagination."""
    
    total: int
    limit: int
    offset: int
    results: List[RemovalRequestListItem]


class SessionLogResponse(BaseModel):
    """Response model for a session log entry."""
    
    id: int
    devin_session_id: int
    timestamp: datetime
    log_level: str
    message: str
    event_type: Optional[str]
    
    class Config:
        from_attributes = True


class LogsResponse(BaseModel):
    """Response model for logs endpoint."""
    
    removal_request_id: int
    logs: List[SessionLogResponse]

# ============================================================================
# ============================================================================

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

# ============================================================================
# ============================================================================

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
                    
                    await self.update_session_status(db, session, details)
                    
                    if session.status != details.status_enum:
                        await self.log_status_change(db, session, details)
                    
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
        session.status = details.status_enum
        
        if details.pull_request:
            session.pr_url = details.pull_request.get('url')
        
        if details.structured_output:
            session.structured_output = json.dumps(details.structured_output)
            
            if isinstance(details.structured_output, dict):
                acu = details.structured_output.get('acu_consumed')
                if acu is not None:
                    session.acu_consumed = acu
        
        if details.status_enum in ['finished', 'expired'] and not session.completed_at:
            session.completed_at = datetime.utcnow()
        
        db.add(session)
    
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
    
    async def update_removal_request_status(self, db: Session, removal_request_id: int):
        """Update removal request status based on session statuses."""
        removal_request = db.query(RemovalRequest).filter_by(id=removal_request_id).first()
        if not removal_request:
            return
        
        sessions = removal_request.sessions
        
        if all(s.status in ['finished', 'expired'] for s in sessions):
            if any(s.status == 'expired' or s.error_message for s in sessions):
                removal_request.status = 'failed'
            else:
                removal_request.status = 'completed'
        elif any(s.status in ['working', 'blocked'] for s in sessions):
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
                provider=removal_request.feature_flag_provider
            )
            
            logger.info(f"Creating Devin session for removal request {removal_request.id}, repository {session.repository}")
            
            devin_session = self.devin_client.create_session(
                prompt=prompt,
                title=f"Remove flag: {removal_request.flag_key}",
                tags=["flag-removal", removal_request.flag_key],
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
    
    def build_removal_prompt(self, flag_key: str, repository: str, provider: Optional[str]) -> str:
        """Build the prompt for Devin to remove a feature flag."""
        prompt = f"""Task: Remove feature flag from codebase

Flag Key: {flag_key}
Repository: {repository}
Provider: {provider or 'Unknown'}

Instructions:
1. Clone the repository
2. Search for all occurrences of the flag key "{flag_key}"
3. Analyze each occurrence and determine safe removal strategy
4. Remove the flag and associated conditional code
5. Ensure code still compiles and tests pass
6. Create a pull request with:
   - Title: "Remove feature flag: {flag_key}"
   - Description: List of files modified and changes made
   - Label: "feature-flag-removal"

Important:
- Do NOT remove code that is still needed
- Preserve the "enabled" code path
- Remove the "disabled" code path
- Run all tests before creating PR
- If tests fail, investigate and fix
- If you need clarification, ask before proceeding

IMPORTANT: Return structured output in this EXACT JSON format:
{{
  "pr_url": "https://github.com/...",
  "files_modified": ["path/to/file1.py", "path/to/file2.js"],
  "occurrences_removed": 12,
  "test_results": "PASSED" or "FAILED" or "SKIPPED",
  "warnings": ["Any warnings or issues encountered"],
  "acu_consumed": 450
}}

If you cannot create a PR, set pr_url to null and explain in warnings.
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

# ============================================================================
# ============================================================================

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

# ============================================================================
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and start background services."""
    global monitor_task, queue_task, devin_client
    
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
    queue = SessionQueue(devin_client, max_concurrent=MAX_CONCURRENT_SESSIONS)
    
    monitor_task = asyncio.create_task(monitor.start())
    queue_task = asyncio.create_task(queue.start())
    
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

# ============================================================================
# ============================================================================

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
        
        if len(body.repositories) > MAX_REPOS_PER_REQUEST:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_REPOS_PER_REQUEST} repositories per request"
            )
        
        removal_request = RemovalRequest(
            flag_key=body.flag_key,
            repositories=json.dumps(body.repositories),
            feature_flag_provider=body.feature_flag_provider,
            status='queued',
            created_by=body.created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(removal_request)
        db.flush()
        
        for repo in body.repositories:
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
                status=req.status,
                created_by=req.created_by,
                created_at=req.created_at,
                updated_at=req.updated_at,
                session_count=len(sessions),
                completed_sessions=sum(1 for s in sessions if s.status in ['finished', 'expired']),
                failed_sessions=sum(1 for s in sessions if s.error_message or s.status == 'expired')
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

# ============================================================================
# ============================================================================

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
        status=removal_request.status,
        created_by=removal_request.created_by,
        created_at=removal_request.created_at,
        updated_at=removal_request.updated_at,
        error_message=removal_request.error_message,
        total_acu_consumed=removal_request.total_acu_consumed,
        sessions=sessions
    )
