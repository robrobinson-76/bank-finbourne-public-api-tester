from __future__ import annotations
import fnmatch

from lusid_mock.models.drive import DriveFile, ScanState, UploadResponse
from lusid_mock.store.drive_store import DriveStore
from lusid_mock.models.control import ScenarioConfig


async def upload_file(
    store: DriveStore,
    config: ScenarioConfig,
    path: str,
    content: bytes,
    content_type: str,
) -> UploadResponse:
    import asyncio
    f = store.put(path, content, content_type)
    is_malware = any(fnmatch.fnmatch(path, pat) for pat in config.malware_path_patterns)
    asyncio.create_task(store.schedule_scan(f.id, config.virus_scan_delay_s, is_malware))
    return UploadResponse(
        id=f.id,
        path=f.path,
        content_type=f.content_type,
        size=f.size,
        created_at=f.created_at,
    )


def get_file_contents(store: DriveStore, file_id: str) -> tuple[str, bytes] | int:
    """Returns (content_type, content) or an HTTP status code on error."""
    f = store.get(file_id)
    if f is None:
        return 404
    if f.scan_state == ScanState.SCANNING:
        return 423
    if f.scan_state == ScanState.MALWARE:
        return 410
    return (f.content_type, f.content)


def delete_file(store: DriveStore, file_id: str) -> bool:
    return store.delete(file_id)
