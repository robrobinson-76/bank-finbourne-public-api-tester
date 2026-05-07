# LUSID Mock Server — API Reference

Base URL: `http://localhost:9000`

Interactive docs: `http://localhost:9000/docs`

---

## Drive API

Mirrors the FINBOURNE LUSID Drive API paths. Point your application's Drive base URL at `http://localhost:9000`.

### `POST /drive/api/files`

Upload a file. Returns immediately with the file in `SCANNING` state.

**Request:** `multipart/form-data`

- `file` — binary file content
- `path` — Drive path string (e.g. `/WIG/inbound/2025-01-01/corr-001.dat`)

**Response 201:**

```json
{
  "id": "uuid",
  "path": "/WIG/inbound/2025-01-01/corr-001.dat",
  "content_type": "application/octet-stream",
  "size": 1024,
  "created_at": "2025-01-01T10:00:00Z"
}
```

---

### `GET /drive/api/files/{id}/contents`

Download file content.

| Status | Meaning |
|---|---|
| 200 | File is clean — returns binary content |
| 423 | Still scanning — retry after `virus_scan_delay_s` |
| 410 | Malware detected — permanent failure |
| 404 | File not found |

---

### `DELETE /drive/api/files/{id}`

Delete a file. Returns `204` on success, `404` if not found.

---

## Workflow API

Mirrors the FINBOURNE LUSID Workflow API paths.

### `POST /workflow/api/tasks`

Create a workflow task. Task starts in `Pending` state and auto-advances on configured timers.

**Request body:**

```json
{
  "correlationId": "corr-001",
  "sourceChannel": "SFTP",
  "driveFilePath": "/WIG/inbound/2025-01-01/corr-001.dat",
  "driveFileId": "uuid-of-uploaded-file",
  "payloadType": "CSV",
  "fields": {
    "anyCustomKey": "anyValue"
  }
}
```

**Response 201:** Full `Task` object (see schema below).

---

### `GET /workflow/api/tasks/{id}`

Get a single task by ID. Returns `404` if not found.

---

### `GET /workflow/api/tasks`

List tasks. Optional query parameter:

- `state` — filter by state: `Pending`, `Processing`, `Complete`, `Error`

**Response:**

```json
{
  "values": [],
  "total_count": 42
}
```

---

### Task Schema

```json
{
  "id": "uuid",
  "state": "Pending | Processing | Complete | Error",
  "correlationId": "corr-001",
  "sourceChannel": "SFTP",
  "driveFilePath": "/WIG/inbound/...",
  "driveFileId": "uuid",
  "payloadType": "CSV",
  "fields": {},
  "result_fields": {},
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "completed_at": "ISO8601 | null"
}
```

---

## Control API

Test harness control endpoints. Not part of the real LUSID API.

### `GET /lusid-mock/control/status`

Current server state.

```json
{
  "files_total": 10,
  "files_scanning": 2,
  "files_clean": 7,
  "files_malware": 1,
  "tasks_pending": 3,
  "tasks_processing": 1,
  "tasks_complete": 15,
  "tasks_error": 2,
  "webhooks_fired": 15,
  "webhooks_failed": 0,
  "config": {}
}
```

---

### `POST /lusid-mock/control/config`

Update scenario configuration. Takes effect immediately, no restart needed.

```json
{
  "virus_scan_delay_s": 0.0,
  "processing_delay_s": 0.0,
  "completion_delay_s": 0.0,
  "error_rate": 0.0,
  "malware_path_patterns": ["*malware*", "*/blocked/*"],
  "webhook_url": "http://your-app/api/v1/lusid/callback",
  "webhook_failure_rate": 0.1
}
```

---

### `POST /lusid-mock/control/tasks/{id}/advance`

Force a task to a specific state immediately, bypassing timers. Use in tests for deterministic control.

```json
{
  "target_state": "Complete",
  "result_fields": {
    "resultFileId": "output-file-uuid",
    "outputCount": "1"
  }
}
```

Valid `target_state` values: `Processing`, `Complete`, `Error`

Returns the updated `Task` object. Returns `404` if task not found or state is invalid.

---

### `GET /lusid-mock/control/events`

Full event log, time-sorted. Useful for asserting on what happened during a test scenario.

```json
[
  {"timestamp": "ISO8601", "event_type": "FILE_UPLOADED", "entity_id": "uuid", "detail": "path=/WIG/... size=1024"},
  {"timestamp": "ISO8601", "event_type": "TASK_CREATED", "entity_id": "uuid", "detail": "correlationId=corr-001 state=Pending"},
  {"timestamp": "ISO8601", "event_type": "TASK_STATE_CHANGED", "entity_id": "uuid", "detail": "state=Processing"},
  {"timestamp": "ISO8601", "event_type": "TASK_STATE_CHANGED", "entity_id": "uuid", "detail": "state=Complete"},
  {"timestamp": "ISO8601", "event_type": "WEBHOOK_FIRED", "entity_id": "uuid", "detail": "status=fired url=http://..."}
]
```

Event types: `FILE_UPLOADED` `FILE_DELETED` `FILE_SCAN_STATE` `TASK_CREATED` `TASK_STATE_CHANGED` `WEBHOOK_FIRED` `WEBHOOK_FAILED` `STORE_RESET`

---

### `POST /lusid-mock/control/reset`

Clear all files, tasks, event log, webhook counters, and reset config to defaults. Returns `204`. Call between test cases for isolation.
