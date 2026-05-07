"""End-to-end scenario: upload payload → create task → manual advance → complete → event log."""
import io
import pytest


def test_full_inbound_to_complete_scenario(client, app):
    from lusid_mock.models.drive import ScanState

    # 1. Upload payload to Drive
    r = client.post(
        "/drive/api/files",
        data={"path": "/WIG/inbound/2025-01-01/e2e-test.dat"},
        files={"file": ("e2e-test.dat", io.BytesIO(b"payload data"), "application/octet-stream")},
    )
    assert r.status_code == 201
    file_id = r.json()["id"]

    # 2. Simulate scan completing (force clean state)
    app.state.drive_store.set_scan_state(file_id, ScanState.CLEAN)

    # 3. Verify file is downloadable
    r = client.get(f"/drive/api/files/{file_id}/contents")
    assert r.status_code == 200
    assert r.content == b"payload data"

    # 4. Create workflow task referencing the Drive file
    task_r = client.post("/workflow/api/tasks", json={
        "correlationId": "e2e-corr-001",
        "sourceChannel": "SFTP",
        "driveFilePath": "/WIG/inbound/2025-01-01/e2e-test.dat",
        "driveFileId": file_id,
        "payloadType": "CSV",
        "fields": {"submittedBy": "test-harness"},
    })
    assert task_r.status_code == 201
    task_id = task_r.json()["id"]
    assert task_r.json()["state"] == "Pending"

    # 5. Manually advance through Processing
    r = client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Processing", "result_fields": {}})
    assert r.json()["state"] == "Processing"

    # 6. Complete with a result
    r = client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={
        "target_state": "Complete",
        "result_fields": {"resultFileId": "result-abc", "outputCount": "1"},
    })
    assert r.json()["state"] == "Complete"
    assert r.json()["result_fields"]["resultFileId"] == "result-abc"

    # 7. Status reflects terminal state
    status = client.get("/lusid-mock/control/status").json()
    assert status["tasks_complete"] == 1
    assert status["tasks_pending"] == 0

    # 8. Event log captures full lifecycle
    events = client.get("/lusid-mock/control/events").json()
    event_types = [e["event_type"] for e in events]
    assert "FILE_UPLOADED" in event_types
    assert "TASK_CREATED" in event_types
    assert "TASK_STATE_CHANGED" in event_types


def test_error_state_scenario(client):
    task_r = client.post("/workflow/api/tasks", json={
        "correlationId": "e2e-error-001",
        "sourceChannel": "EMAIL",
        "driveFilePath": "/WIG/inbound/error.dat",
        "driveFileId": "file-err",
        "payloadType": "PDF",
        "fields": {},
    })
    task_id = task_r.json()["id"]

    client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Processing", "result_fields": {}})
    r = client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Error", "result_fields": {"reason": "processing failed"}})
    assert r.json()["state"] == "Error"
    assert r.json()["completed_at"] is not None
    assert client.get("/lusid-mock/control/status").json()["tasks_error"] == 1
