from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel


class TaskState(str, Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETE = "Complete"
    ERROR = "Error"


class TaskCreateRequest(BaseModel):
    correlationId: str
    sourceChannel: str
    driveFilePath: str
    driveFileId: str
    payloadType: str | None = None
    submittedAt: str | None = None
    # arbitrary extra metadata fields
    fields: dict[str, str] = {}


class Task(BaseModel):
    id: str
    state: TaskState
    correlationId: str
    sourceChannel: str
    driveFilePath: str
    driveFileId: str
    payloadType: str | None
    fields: dict[str, str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    result_fields: dict[str, Any] = {}


class TaskListResponse(BaseModel):
    values: list[Task]
    total_count: int
