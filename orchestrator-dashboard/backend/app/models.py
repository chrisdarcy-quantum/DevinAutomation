"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


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


class StatusUpdateEvent(BaseModel):
    """SSE event for status updates."""
    
    removal_id: int
    status: str
    updated_at: str
    sessions: List[Dict[str, Any]]


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str
    details: Optional[Dict[str, Any]] = None
