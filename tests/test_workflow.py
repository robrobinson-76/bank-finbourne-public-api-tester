import pytest


TASK_PAYLOAD = {
    "correlationId": "corr-001",
    "sourceChannel": "SFTP",
    "driveFilePath": "/WIG/inbound/2025-01-01/corr-001.dat",
    "driveFileId": "file-abc",
    "payloadType": "CSV",
    "fields": {},
}


def test_create_task_returns_201(client):
    r = client.post("/workflow/api/tasks", json=TASK_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["state"] == "Pending"
    assert body["correlationId"] == "corr-001"


def test_get_task(client):
    task_id = client.post("/workflow/api/tasks", json=TASK_PAYLOAD).json()["id"]
    r = client.get(f"/workflow/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["id"] == task_id


def test_get_task_not_found(client):
    r = client.get("/workflow/api/tasks/no-such-id")
    assert r.status_code == 404


def test_list_tasks(client):
    client.post("/workflow/api/tasks", json=TASK_PAYLOAD)
    client.post("/workflow/api/tasks", json={**TASK_PAYLOAD, "correlationId": "corr-002"})
    r = client.get("/workflow/api/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["total_count"] == 2


def test_list_tasks_state_filter(client):
    task_id = client.post("/workflow/api/tasks", json=TASK_PAYLOAD).json()["id"]
    client.post(f"/lusid-mock/control/tasks/{task_id}/advance", json={"target_state": "Processing", "result_fields": {}})
    r = client.get("/workflow/api/tasks?state=Processing")
    assert r.status_code == 200
    assert r.json()["total_count"] == 1


def test_task_fields_round_trip(client):
    payload = {**TASK_PAYLOAD, "fields": {"customKey": "customValue"}}
    task_id = client.post("/workflow/api/tasks", json=payload).json()["id"]
    body = client.get(f"/workflow/api/tasks/{task_id}").json()
    assert body["fields"]["customKey"] == "customValue"
