from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class ScenarioConfig(BaseModel):
    virus_scan_delay_s: float = 2.0
    processing_delay_s: float = 3.0
    completion_delay_s: float = 5.0
    error_rate: float = 0.0          # 0.0–1.0 probability a task ends in Error
    malware_path_patterns: list[str] = []
    webhook_url: str | None = None
    webhook_failure_rate: float = 0.0


class EventEntry(BaseModel):
    timestamp: datetime
    event_type: str
    entity_id: str
    detail: str


class StatusResponse(BaseModel):
    files_total: int
    files_scanning: int
    files_clean: int
    files_malware: int
    tasks_pending: int
    tasks_processing: int
    tasks_complete: int
    tasks_error: int
    webhooks_fired: int
    webhooks_failed: int
    config: ScenarioConfig


class AdvanceRequest(BaseModel):
    target_state: str  # "Processing", "Complete", "Error"
    result_fields: dict = {}
