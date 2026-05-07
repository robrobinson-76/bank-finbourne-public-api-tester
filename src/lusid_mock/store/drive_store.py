from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone

from lusid_mock.models.drive import DriveFile, ScanState
from lusid_mock.models.control import EventEntry


class DriveStore:
    def __init__(self) -> None:
        self._files: dict[str, DriveFile] = {}
        self._events: list[EventEntry] = []
        self._config_ref: dict = {}  # injected by app at startup

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _log(self, event_type: str, entity_id: str, detail: str) -> None:
        self._events.append(EventEntry(
            timestamp=self._now(),
            event_type=event_type,
            entity_id=entity_id,
            detail=detail,
        ))

    def put(self, path: str, content: bytes, content_type: str) -> DriveFile:
        file_id = str(uuid.uuid4())
        f = DriveFile(
            id=file_id,
            path=path,
            content=content,
            content_type=content_type,
            size=len(content),
            scan_state=ScanState.SCANNING,
            created_at=self._now(),
        )
        self._files[file_id] = f
        self._log("FILE_UPLOADED", file_id, f"path={path} size={len(content)}")
        return f

    def get(self, file_id: str) -> DriveFile | None:
        return self._files.get(file_id)

    def delete(self, file_id: str) -> bool:
        f = self._files.pop(file_id, None)
        if f:
            self._log("FILE_DELETED", file_id, f"path={f.path}")
        return f is not None

    def set_scan_state(self, file_id: str, state: ScanState) -> None:
        f = self._files.get(file_id)
        if f:
            self._files[file_id] = f.model_copy(update={"scan_state": state})
            self._log("FILE_SCAN_STATE", file_id, f"state={state}")

    def counts(self) -> dict[str, int]:
        states = [f.scan_state for f in self._files.values()]
        return {
            "total": len(states),
            "scanning": states.count(ScanState.SCANNING),
            "clean": states.count(ScanState.CLEAN),
            "malware": states.count(ScanState.MALWARE),
        }

    def reset(self) -> None:
        self._files.clear()
        self._log("STORE_RESET", "drive", "all files cleared")

    async def schedule_scan(self, file_id: str, delay_s: float, is_malware: bool) -> None:
        await asyncio.sleep(delay_s)
        target = ScanState.MALWARE if is_malware else ScanState.CLEAN
        self.set_scan_state(file_id, target)
