import io
import pytest


TASK_PAYLOAD = {
    "correlationId": "corr-ctrl",
    "sourceChannel": "EMAIL",
    "driveFilePath": "/WIG/inbound/2025-01-01/corr-ctrl.dat",
    "driveFileId": "file-xyz",
    "payloadType": "PDF",
    "fields": {},
}


def test_status_empty(client):
    r = client.get("/lusid-mock/control/status")
    assert r.status_code == 200
    body = r.json()
    assert body["files_total"] == 0
    assert body["tasks_pending"] == 0


def test_status_reflects_uploads_and_tasks(client):
    client.post("/drive/api/files", data={"path": "/f"}, files={"file": ("f", io.BytesIO(b"x"), "application/octet-stream")})
    client.post("/workflow/api/tasks", json=TASK_PAYLOAD)
    body = client.get("/lusid-mock/control/status").json()
    assert body["files_total"] == 1
    assert body["tasks_pending"] == 1


def test_advance_task_to_processing(client):
    task_id = client.post("/workflow/api/tasks", json=TASK_PAYLOAD).json()["id"]
    r = client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Processing", "result_fields": {}})
    assert r.status_code == 200
    assert r.json()["state"] == "Processing"


def test_advance_task_to_complete_with_result(client):
    task_id = client.post("/workflow/api/tasks", json=TASK_PAYLOAD).json()["id"]
    client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Processing", "result_fields": {}})
    r = client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Complete", "result_fields": {"outputFileId": "out-123"}})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "Complete"
    assert body["result_fields"]["outputFileId"] == "out-123"
    assert body["completed_at"] is not None


def test_advance_unknown_task_returns_404(client):
    r = client.post("/lusid-mock/control/tasks/no-such/advance", json={"target_state": "Complete", "result_fields": {}})
    assert r.status_code == 404


def test_update_config(client):
    new_cfg = {"virus_scan_delay_s": 10.0, "processing_delay_s": 30.0, "completion_delay_s": 60.0, "error_rate": 0.5, "malware_path_patterns": [], "webhook_url": "http://localhost/cb", "webhook_failure_rate": 0.0}
    r = client.post("/lusid-mock/control/config", json=new_cfg)
    assert r.status_code == 200
    assert r.json()["webhook_url"] == "http://localhost/cb"
    status = client.get("/lusid-mock/control/status").json()
    assert status["config"]["webhook_url"] == "http://localhost/cb"


def test_reset_clears_all_state(client):
    client.post("/drive/api/files", data={"path": "/f"}, files={"file": ("f", io.BytesIO(b"x"), "application/octet-stream")})
    client.post("/workflow/api/tasks", json=TASK_PAYLOAD)
    client.post("/lusid-mock/control/reset")
    body = client.get("/lusid-mock/control/status").json()
    assert body["files_total"] == 0
    assert body["tasks_pending"] == 0


def test_events_log_populated(client):
    client.post("/workflow/api/tasks", json=TASK_PAYLOAD)
    r = client.get("/lusid-mock/control/events")
    assert r.status_code == 200
    events = r.json()
    assert any(e["event_type"] == "TASK_CREATED" for e in events)
