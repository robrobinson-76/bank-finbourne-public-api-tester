from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class ScanState(str, Enum):
    SCANNING = "SCANNING"
    CLEAN = "CLEAN"
    MALWARE = "MALWARE"


class DriveFile(BaseModel):
    id: str
    path: str
    content_type: str
    size: int
    scan_state: ScanState
    created_at: datetime
    content: bytes

    model_config = {"arbitrary_types_allowed": True}


class UploadResponse(BaseModel):
    id: str
    path: str
    content_type: str
    size: int
    created_at: datetime


class FileMetadata(BaseModel):
    id: str
    path: str
    content_type: str
    size: int
    scan_state: ScanState
    created_at: datetime
