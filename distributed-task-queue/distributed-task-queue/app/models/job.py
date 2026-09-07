import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlmodel import SQLModel, Field, Column, JSON

class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"

class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    idempotency_key: str = Field(index=True, unique=True, nullable=False)
    job_type: str = Field(index=True, nullable=False)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))