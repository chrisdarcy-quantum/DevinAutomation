"""Main FastAPI application for the Feature Flag Removal Orchestration Dashboard."""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from app.database import get_db, init_db, RemovalRequest, DevinSession, SessionLog
from app.models import (
    CreateRemovalRequest,
    RemovalRequestResponse,
    RemovalRequestListResponse,
    RemovalRequestListItem,
    SessionResponse,
    LogsResponse,
    SessionLogResponse,
    ErrorResponse
)
from app.services import SessionMonitor, SessionQueue
from app.devin_api_client import DevinAPIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_REPOS_PER_REQUEST = 5
MAX_CONCURRENT_SESSIONS = 20

app = FastAPI(
    title="Feature Flag Removal Orchestration API",
    description="API for orchestrating feature flag removal using Devin AI",
    version="1.0.0"
)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

monitor_task = None
queue_task = None
devin_client = None


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


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/removals", response_model=RemovalRequestResponse, status_code=201)
@limiter.limit("5/minute")
async def create_removal(
    request: Request,
    body: CreateRemovalRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new feature flag removal request.
    
    This will create Devin sessions for each repository.
    Rate limited to 5 requests per minute per user.
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
        db.flush()  # Get the ID
        
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
                
                await asyncio.sleep(5)  # Poll every 5 seconds
                
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
        status=removal_request.status,
        created_by=removal_request.created_by,
        created_at=removal_request.created_at,
        updated_at=removal_request.updated_at,
        error_message=removal_request.error_message,
        total_acu_consumed=removal_request.total_acu_consumed,
        sessions=sessions
    )
