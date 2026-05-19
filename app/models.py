"""
Pydantic models for data validation.
This file defines all the data structures used in the API.
Pydantic automatically validates and converts incoming data.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from enum import Enum
from datetime import datetime

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(BaseModel):
    assignee: str = Field(..., description="Person assigned to task")
    task: str = Field(..., description="What needs to be done")
    deadline: str = Field(default="TBD", description="Due date (ISO format or 'TBD')")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    
    @validator('assignee', 'task')
    def non_empty_strings(cls, v):
        if not v or not v.strip():
            raise ValueError('Must not be empty')
        return v.strip()

class Meeting(BaseModel):
    meeting_id: str = Field(..., description="Unique meeting ID")
    filename: str = Field(..., description="Original filename")
    duration_seconds: int = Field(..., ge=0, description="Audio duration")
    transcript: str = Field(..., description="Full meeting transcript")
    tasks: List[Task] = Field(default_factory=list, description="Extracted tasks")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class UploadResponse(BaseModel):
    job_id: str = Field(..., description="Unique job ID for tracking")
    status: JobStatus = Field(default=JobStatus.QUEUED)
    message: str = Field(default="File queued for processing")
    filename: str = Field(..., description="Name of uploaded file")
    
    class Config:
        use_enum_values = True

class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    progress: Optional[str] = Field(default=None, description="Current processing step")
    transcript: Optional[str] = Field(default=None, description="Full meeting transcript (if completed)")
    tasks: Optional[List[Task]] = Field(default=None, description="Extracted tasks (if completed)")
    error: Optional[str] = Field(default=None, description="Error message (if failed)")
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}

class HealthCheckResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message")
    error_code: str = Field(default="unknown_error")