"""
Integration tests against a real running uvicorn server.

The in-process TestClient tests (test_drive.py, test_workflow.py, etc.) use
FastAPI's synchronous test client and bypass asyncio. That means asyncio
background tasks — the virus scan timer and the task auto-advance state
machine — never actually fire during those tests. Manual /advance calls are
used instead.

These tests start a real uvicorn instance on port 9001 and a webhook capture
server on port 9002. They issue real HTTP requests and wait for async
background work to complete. This is the only way to verify that:

  - Files transition SCANNING → CLEAN/MALWARE after the scan delay
  - Tasks auto-advance Pending → Processing → Complete/Error on schedule
  - Webhooks are delivered over real HTTP when a task completes
  - Error rate and malware path pattern configs work end-to-end
"""
from __future__ import annotations

import io
import time
import threading

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request

from lusid_mock.app import create_app

LIVE_HOST = "127.0.0.1"
LIVE_PORT = 9001
CAPTURE_PORT = 9002
BASE = f"http://{LIVE_HOST}:{LIVE_PORT}"
CAPTURE_BASE = f"http://{LIVE_HOST}:{CAPTURE_PORT}"

# Short delays — fast enough for CI, long enough to exercise the real async path
FAST_CONFIG = {
    "virus_scan_delay_s": 0.3,
    "processing_delay_s": 0.3,
    "completion_delay_s": 0.3,
    "error_rate": 0.0,
    "malware_path_patterns": [],
    "webhook_url": None,
    "webhook_failure_rate": 0.0,
}

TASK_PAYLOAD = {
    "correlationId": "live-corr-001",
    "sourceChannel": "SFTP",
    "driveFilePath": "/WIG/inbound/2025-01-01/live.dat",
    "driveFileId": "placeholder",
    "payloadType": "CSV",
    "fields": {},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _poll_task_state(task_id: str, target: str, timeout: float = 5.0) -> dict:
    """Poll until the task reaches target state or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = httpx.get(f"{BASE}/workflow/api/tasks/{task_id}", timeout=5)
        if r.json()["state"] == target:
            return r.json()
        time.sleep(0.05)
    raise TimeoutError(f"Task {task_id} did not reach '{target}' within {timeout}s")


def _poll_file_status(file_id: str, expected_http: int, timeout: float = 5.0) -> httpx.Response:
    """Poll until GET /contents returns the expected HTTP status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = httpx.get(f"{BASE}/drive/api/files/{file_id}/contents", timeout=5)
        if r.status_code == expected_http:
            return r
        time.sleep(0.05)
    raise TimeoutError(f"File {file_id} did not reach HTTP {expected_http} within {timeout}s")


def _poll_webhooks(captured: list, count: int, timeout: float = 5.0) -> None:
    """Poll until at least `count` webhooks have been captured."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(captured) >= count:
            return
        time.sleep(0.05)
    raise TimeoutError(f"Only {len(captured)}/{count} webhooks captured within {timeout}s")


def _upload(file_id_hint: str = "live.dat", content: bytes = b"payload") -> dict:
    r = httpx.post(
        f"{BASE}/drive/api/files",
        data={"path": f"/WIG/inbound/{file_id_hint}"},
        files={"file": (file_id_hint, io.BytesIO(content), "application/octet-stream")},
        timeout=5,
    )
    assert r.status_code == 201
    return r.json()


def _create_task(corr_id: str = "live-corr", drive_file_id: str = "fid") -> dict:
    r = httpx.post(f"{BASE}/workflow/api/tasks", json={
        **TASK_PAYLOAD,
        "correlationId": corr_id,
        "driveFileId": drive_file_id,
    }, timeout=5)
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Module-scoped fixtures: start servers once per module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_server():
    """Start a real uvicorn server on LIVE_PORT. Shared across all live tests."""
    app = create_app()
    config = uvicorn.Config(app, host=LIVE_HOST, port=LIVE_PORT, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait until server is accepting requests
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{BASE}/lusid-mock/control/status", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Live server on {LIVE_PORT} did not start in time")
    yield BASE
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="module")
def webhook_capture():
    """
    Lightweight FastAPI server on CAPTURE_PORT that records POST payloads.
    Yields (callback_url, captured_list).
    """
    captured: list[dict] = []
    cap_app = FastAPI()

    @cap_app.post("/callback")
    async def callback(request: Request):
        captured.append(await request.json())
        return {"ok": True}

    config = uvicorn.Config(cap_app, host=LIVE_HOST, port=CAPTURE_PORT, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)
    yield (f"{CAPTURE_BASE}/callback", captured)
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(autouse=True)
def reset_and_configure(live_server):
    """Reset server state and apply fast config before each live test."""
    with httpx.Client() as c:
        c.post(f"{live_server}/lusid-mock/control/reset", timeout=5)
        c.post(f"{live_server}/lusid-mock/control/config", json=FAST_CONFIG, timeout=5)
    yield


# ---------------------------------------------------------------------------
# Drive: async scan simulation
# ---------------------------------------------------------------------------

class TestDriveLive:
    def test_file_auto_transitions_to_clean(self, live_server):
        """After scan delay, file transitions from SCANNING to CLEAN."""
        body = _upload()
        file_id = body["id"]
        # Immediately: still scanning
        r = httpx.get(f"{BASE}/drive/api/files/{file_id}/contents", timeout=5)
        assert r.status_code == 423, "Expected 423 (scanning) immediately after upload"
        # After delay: CLEAN
        r = _poll_file_status(file_id, expected_http=200)
        assert r.content == b"payload"

    def test_malware_pattern_auto_transitions_to_malware(self, live_server):
        """File matching a malware pattern transitions to MALWARE after scan delay."""
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "malware_path_patterns": ["*evil*"],
        }, timeout=5)
        body = _upload(file_id_hint="evil-payload.dat")
        file_id = body["id"]
        r = _poll_file_status(file_id, expected_http=410)
        assert r.status_code == 410

    def test_clean_file_is_not_affected_by_malware_pattern(self, live_server):
        """Non-matching files still go CLEAN even when a malware pattern is set."""
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "malware_path_patterns": ["*evil*"],
        }, timeout=5)
        body = _upload(file_id_hint="safe-payload.dat")
        file_id = body["id"]
        r = _poll_file_status(file_id, expected_http=200)
        assert r.status_code == 200

    def test_delete_file_after_scan(self, live_server):
        """Delete works on a clean file after scan completes."""
        body = _upload()
        file_id = body["id"]
        _poll_file_status(file_id, expected_http=200)
        r = httpx.delete(f"{BASE}/drive/api/files/{file_id}", timeout=5)
        assert r.status_code == 204
        r = httpx.get(f"{BASE}/drive/api/files/{file_id}/contents", timeout=5)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Workflow: async state machine
# ---------------------------------------------------------------------------

class TestWorkflowLive:
    def test_task_auto_advances_to_complete(self, live_server):
        """Task created as Pending and auto-advances to Complete within timeout."""
        task = _create_task()
        task_id = task["id"]
        assert task["state"] == "Pending"
        result = _poll_task_state(task_id, "Complete")
        assert result["completed_at"] is not None

    def test_task_passes_through_processing(self, live_server):
        """Task is observable in Processing state before reaching Complete."""
        task = _create_task()
        task_id = task["id"]
        # Poll for Processing (intermediate state)
        _poll_task_state(task_id, "Processing")
        # Then continues to Complete
        _poll_task_state(task_id, "Complete")

    def test_task_auto_advances_to_error_when_rate_is_1(self, live_server):
        """error_rate=1.0 guarantees every task ends in Error."""
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "error_rate": 1.0,
        }, timeout=5)
        task = _create_task()
        result = _poll_task_state(task["id"], "Error")
        assert result["completed_at"] is not None

    def test_list_filter_reflects_live_state(self, live_server):
        """GET /workflow/api/tasks?state= returns correct counts after auto-advance."""
        _create_task(corr_id="live-a")
        _create_task(corr_id="live-b")
        # Wait for both to complete
        tasks = httpx.get(f"{BASE}/workflow/api/tasks", timeout=5).json()["values"]
        for t in tasks:
            _poll_task_state(t["id"], "Complete")
        r = httpx.get(f"{BASE}/workflow/api/tasks?state=Complete", timeout=5)
        assert r.json()["total_count"] == 2
        r = httpx.get(f"{BASE}/workflow/api/tasks?state=Pending", timeout=5)
        assert r.json()["total_count"] == 0

    def test_status_counts_update_after_auto_advance(self, live_server):
        """Control status reflects task state counts as machine runs."""
        task = _create_task()
        _poll_task_state(task["id"], "Complete")
        status = httpx.get(f"{BASE}/lusid-mock/control/status", timeout=5).json()
        assert status["tasks_complete"] == 1
        assert status["tasks_pending"] == 0
        assert status["tasks_processing"] == 0


# ---------------------------------------------------------------------------
# Webhook: real HTTP delivery on task completion
# ---------------------------------------------------------------------------

class TestWebhookLive:
    def test_webhook_fires_on_auto_complete(self, live_server, webhook_capture):
        """Webhook is delivered over real HTTP when a task auto-advances to Complete."""
        callback_url, captured = webhook_capture
        captured.clear()
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "webhook_url": callback_url,
        }, timeout=5)
        task = _create_task()
        _poll_task_state(task["id"], "Complete")
        _poll_webhooks(captured, count=1)
        payload = captured[-1]
        assert payload["task_id"] == task["id"]
        assert payload["state"] == "Complete"
        assert payload["correlation_id"] == "live-corr"

    def test_webhook_not_fired_on_error_state(self, live_server, webhook_capture):
        """Webhook is NOT fired when a task ends in Error (Complete only)."""
        callback_url, captured = webhook_capture
        captured.clear()
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG,
            "webhook_url": callback_url,
            "error_rate": 1.0,
        }, timeout=5)
        task = _create_task()
        _poll_task_state(task["id"], "Error")
        time.sleep(0.3)  # Give any mistaken webhook time to arrive
        assert len(captured) == 0, "Webhook should not fire for Error state"

    def test_webhook_failure_rate_recorded_in_status(self, live_server, webhook_capture):
        """webhook_failure_rate=1.0 causes all webhooks to fail and status reflects it."""
        callback_url, captured = webhook_capture
        captured.clear()
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG,
            "webhook_url": callback_url,
            "webhook_failure_rate": 1.0,
        }, timeout=5)
        task = _create_task()
        _poll_task_state(task["id"], "Complete")
        time.sleep(0.3)
        status = httpx.get(f"{BASE}/lusid-mock/control/status", timeout=5).json()
        assert status["webhooks_failed"] == 1
        assert status["webhooks_fired"] == 0
        assert len(captured) == 0

    def test_multiple_tasks_each_fire_webhook(self, live_server, webhook_capture):
        """Each completing task fires its own webhook."""
        callback_url, captured = webhook_capture
        captured.clear()
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "webhook_url": callback_url,
        }, timeout=5)
        t1 = _create_task(corr_id="wh-a")
        t2 = _create_task(corr_id="wh-b")
        _poll_task_state(t1["id"], "Complete")
        _poll_task_state(t2["id"], "Complete")
        _poll_webhooks(captured, count=2)
        corr_ids = {w["correlation_id"] for w in captured}
        assert corr_ids == {"wh-a", "wh-b"}


# ---------------------------------------------------------------------------
# Full pipeline: upload → task → auto-advance → complete → webhook → events
# ---------------------------------------------------------------------------

class TestFullPipelineLive:
    def test_complete_wig_inbound_flow(self, live_server, webhook_capture):
        """
        Exercises the complete WIG inbound scenario end-to-end with real async
        timers: upload payload, create task, auto-advance through states, receive
        webhook, verify event log records every step.
        """
        callback_url, captured = webhook_capture
        captured.clear()
        httpx.post(f"{BASE}/lusid-mock/control/config", json={
            **FAST_CONFIG, "webhook_url": callback_url,
        }, timeout=5)

        # 1. Upload payload
        file_body = _upload("pipeline-test.dat", content=b"corr-pipeline payload")
        file_id = file_body["id"]

        # 2. Wait for file to be clean
        _poll_file_status(file_id, expected_http=200)

        # 3. Create workflow task
        task = httpx.post(f"{BASE}/workflow/api/tasks", json={
            "correlationId": "pipeline-corr",
            "sourceChannel": "SFTP",
            "driveFilePath": "/WIG/inbound/pipeline-test.dat",
            "driveFileId": file_id,
            "payloadType": "CSV",
            "fields": {"submittedBy": "live-test"},
        }, timeout=5).json()
        assert task["state"] == "Pending"

        # 4. Auto-advance runs: Pending → Processing → Complete
        _poll_task_state(task["id"], "Complete")

        # 5. Webhook delivered
        _poll_webhooks(captured, count=1)
        wh = captured[0]
        assert wh["task_id"] == task["id"]
        assert wh["state"] == "Complete"

        # 6. Status shows terminal counts
        status = httpx.get(f"{BASE}/lusid-mock/control/status", timeout=5).json()
        assert status["tasks_complete"] == 1
        assert status["files_clean"] == 1
        assert status["webhooks_fired"] == 1

        # 7. Event log has all lifecycle events
        events = httpx.get(f"{BASE}/lusid-mock/control/events", timeout=5).json()
        event_types = [e["event_type"] for e in events]
        assert "FILE_UPLOADED" in event_types
        assert "FILE_SCAN_STATE" in event_types
        assert "TASK_CREATED" in event_types
        assert "TASK_STATE_CHANGED" in event_types
        assert "WEBHOOK_FIRED" in event_types

    def test_reset_clears_live_server_state(self, live_server):
        """POST /reset on the live server wipes all files and tasks."""
        _upload()
        _create_task()
        httpx.post(f"{BASE}/lusid-mock/control/reset", timeout=5)
        status = httpx.get(f"{BASE}/lusid-mock/control/status", timeout=5).json()
        assert status["files_total"] == 0
        assert status["tasks_pending"] == 0
