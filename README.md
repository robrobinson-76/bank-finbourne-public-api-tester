# LUSID Mock Server

An in-memory mock of the FINBOURNE LUSID API surfaces (Drive, Workflow, Notification) that lets you test applications that depend on LUSID locally — no FINBOURNE credentials or network access required.

Point your application at `http://localhost:9000` instead of the real LUSID URL. The mock accepts the same API paths, stores state in memory, auto-advances task state machines, and fires webhooks to your callback endpoint.

---

## What it mocks

| LUSID Surface | Endpoints |
|---|---|
| **Drive** | `POST /drive/api/files` — upload payload; `GET /drive/api/files/{id}/contents` — download (with scan simulation); `DELETE /drive/api/files/{id}` |
| **Workflow** | `POST /workflow/api/tasks` — create task; `GET /workflow/api/tasks/{id}` — get; `GET /workflow/api/tasks?state=` — list/filter |
| **Control** | `GET /lusid-mock/control/status` — server state; `POST /lusid-mock/control/config` — scenario config; `POST /lusid-mock/control/tasks/{id}/advance` — force state transition; `GET /lusid-mock/control/events` — event log; `POST /lusid-mock/control/reset` — clear all state |

Interactive API docs: `http://localhost:9000/docs`

---

## Quick Start

**Prerequisites:** Docker, Python 3.11+, [uv](https://github.com/astral-sh/uv)

### Docker (recommended)

```bash
docker compose up -d
```

Server is ready when `http://localhost:9000/lusid-mock/control/status` returns 200.

### Local (development)

```bash
uv sync
uv run python -m lusid_mock
```

---

## How it works

### Drive — virus scan simulation

Files enter `SCANNING` state on upload. After a configurable delay (default 2s) they transition to `CLEAN`. Files whose path matches a configured malware pattern transition to `MALWARE` instead.

- `HTTP 423` — file still scanning (retry after delay)
- `HTTP 410` — file is malware (permanent failure)
- `HTTP 200` — file is clean, content returned

### Workflow — auto-advancing state machine

Tasks are created in `Pending` state. A background coroutine automatically advances them:

```
Pending → Processing (after processing_delay_s, default 3s)
        → Complete   (after completion_delay_s, default 5s)
        → Error      (if error_rate > 0)
```

On `Complete`, the server fires a webhook POST to `webhook_url` (if configured).

### Control API — scripted test scenarios

Configure behaviour for each test scenario:

```bash
# Set webhook target and simulate 20% error rate
curl -X POST http://localhost:9000/lusid-mock/control/config \
  -H "Content-Type: application/json" \
  -d '{
    "virus_scan_delay_s": 1.0,
    "processing_delay_s": 2.0,
    "completion_delay_s": 3.0,
    "error_rate": 0.2,
    "malware_path_patterns": ["*malware*"],
    "webhook_url": "http://your-app/api/v1/lusid/callback",
    "webhook_failure_rate": 0.0
  }'

# Manually force a task to Complete (bypasses timer)
curl -X POST http://localhost:9000/lusid-mock/control/tasks/{task_id}/advance \
  -H "Content-Type: application/json" \
  -d '{"target_state": "Complete", "result_fields": {"resultFileId": "out-abc"}}'

# Check server state
curl http://localhost:9000/lusid-mock/control/status

# View full event log
curl http://localhost:9000/lusid-mock/control/events

# Reset all state between test runs
curl -X POST http://localhost:9000/lusid-mock/control/reset
```

---

## Example: WIG inbound flow

```bash
# 1. Upload payload to mock Drive
curl -X POST http://localhost:9000/drive/api/files \
  -F "path=/WIG/inbound/2025-01-01/corr-001.dat" \
  -F "file=@payload.dat"
# → {"id": "abc123", "path": "...", "size": 1024, ...}

# 2. Create workflow task
curl -X POST http://localhost:9000/workflow/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "correlationId": "corr-001",
    "sourceChannel": "SFTP",
    "driveFilePath": "/WIG/inbound/2025-01-01/corr-001.dat",
    "driveFileId": "abc123",
    "payloadType": "CSV"
  }'
# → {"id": "task-xyz", "state": "Pending", ...}

# 3. Task auto-advances: Pending → Processing → Complete
# Webhook fires to webhook_url when Complete

# 4. Check status
curl http://localhost:9000/lusid-mock/control/status
```

---

## Running Tests

```bash
uv sync
uv run pytest tests/ -v
```

25 tests covering Drive, Workflow, Control API, and end-to-end scenarios.

---

## Project Structure

```
src/lusid_mock/
├── models/        Pydantic models — DriveFile, Task, ScenarioConfig
├── store/         In-memory state — DriveStore, TaskStore + event log
├── services/      Business logic — drive, workflow, webhook services
├── api/           FastAPI routers — /drive, /workflow, /lusid-mock/control
└── app.py         App assembly
tests/
├── test_drive.py
├── test_workflow.py
├── test_control.py
└── test_e2e.py
```

---

## Documentation

| Doc | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, design decisions, extension guide |
| [docs/AGENTS.md](docs/AGENTS.md) | Full API reference for all endpoints |
