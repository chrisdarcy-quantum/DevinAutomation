"""Background services for monitoring and managing Devin sessions."""

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.database import SessionLocal, DevinSession, RemovalRequest, SessionLog
from app.devin_api_client import DevinAPIClient

logger = logging.getLogger(__name__)

MAX_CONCURRENT_SESSIONS = 20
POLL_INTERVAL = 10  # seconds
TIMEOUT_THRESHOLD = 900  # 15 minutes in seconds


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
