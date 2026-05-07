# LUSID Mock Server — Claude Code Project Context

## Purpose

This project is an in-memory mock of the FINBOURNE LUSID API (Drive, Workflow, Notification). It lets applications that depend on LUSID — such as the Workflow Integration Gateway (WIG) — run and be tested locally without real FINBOURNE credentials or network access.

The mock accepts the same HTTP paths as LUSID, stores state in memory, auto-advances task state machines via async background tasks, and fires webhooks to a configured callback URL.

## Key Documentation

- **docs/ARCHITECTURE.md** — layers, state machine design, scenario config, design decisions
- **docs/AGENTS.md** — full API reference for all endpoints (Drive, Workflow, Control)

## Quick Start

```bash
uv sync
uv run python -m lusid_mock        # runs on port 9000
# or
docker compose up -d
```

Tests (no external dependencies):

```bash
uv run pytest tests/ -v
```

## Critical Constraints

- All state is in-memory — no database, no external dependencies
- The mock exposes the same paths as real LUSID so consuming apps need zero code changes to switch targets
- Control API (`/lusid-mock/control/*`) is test-only — not part of the real LUSID API surface
- No authentication — auth is out of scope for this mock
- `POST /lusid-mock/control/reset` must be called between test cases for isolation

## Architecture Pattern

```
HTTP client (WIG / tests)
        ↓
   FastAPI Routers  (api/)
        ↓
   Service Layer  (services/)
        ↓
   In-Memory Stores  (store/)
        ↓
   Pydantic Models  (models/)
```

## Project Structure

```
src/lusid_mock/
├── models/      DriveFile, Task, ScenarioConfig, EventEntry
├── store/       DriveStore, TaskStore (in-memory, with event log)
├── services/    drive_service, workflow_service, webhook_service
├── api/         FastAPI routers: /drive, /workflow, /lusid-mock/control
└── app.py       App factory (create_app)
tests/
├── conftest.py  Shared fixtures — TestClient + auto-reset
├── test_drive.py
├── test_workflow.py
├── test_control.py
└── test_e2e.py
```

The codebase is located at `C:\dev\clio-git\bank-finbourne-public-api-tester\`.
