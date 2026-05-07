# LUSID Mock Server — Design Document

*Authored: May 2026. This document records the original design decisions made when building this project.*

---

## Context and Motivation

### Reference Architecture

This project was designed against the **Workflow Integration Gateway (WIG)** architecture document (April 2026 draft, author: Rob, Data Architect). The WIG is a Java/Spring Boot integration component that:

- Accepts items from five inbound channels: SFTP, Email (IMAP), SWIFT MT, Fax/OCR, and Web Feedback
- Wraps each item in a standard envelope and uploads the payload to **LUSID Drive** (FINBOURNE SaaS file storage)
- Creates a **LUSID Workflow task** referencing the Drive file (claim-check pattern — payload body in Drive, only metadata in the task fields)
- Waits for LUSID to complete the workflow task, detecting completion via webhook (primary) and scheduled polling (safety net)
- Downloads the result payload from Drive and dispatches it to downstream systems (IBM MQ, Kafka) based on data-driven routing config

Key WIG design principles relevant to this mock:

- **AI-agentic buildability** — every component independently testable in a containerised sandbox
- **Zero external dependencies in the test harness** — mock services simulate all external systems
- **At-least-once delivery** — Kafka offset committed only after Drive upload + task create + state store update all succeed

### The Problem This Mock Solves

The WIG application calls the real FINBOURNE LUSID API. LUSID is a SaaS product — it requires credentials, network access, and a provisioned tenant. This makes local development and automated testing difficult.

This mock server fills that gap: it exposes the same HTTP paths as LUSID (Drive, Workflow, Notification) and responds identically, but runs in-process with in-memory state and no external dependencies. The WIG (or any other consumer) can point at `http://localhost:9000` and operate without code changes.

---

## Scope Decisions

These decisions were made explicitly before implementation:

| Decision | Choice | Rationale |
|---|---|---|
| **Authentication** | Out of scope (Phase 1) | Adding OAuth mock complexity before functional paths are validated adds noise without value. Consuming apps skip auth or use any dummy Bearer token. |
| **Port** | 9000 | Avoids clash with other local services (8000, 8001 used by bank-ods reference project). |
| **Task auto-advance** | In scope (Phase 1) | The async timer-driven state machine (Pending → Processing → Complete) is the most important behavior to mock. Without it, tests can only verify synchronous path — not the actual integration pattern. |
| **Workflow simulation** (Luminesce workers, result generation) | Phase 2 | The WIG doesn't care how LUSID processes the task internally, only that it completes with result fields. Scripted completion via the Control API covers Phase 1 needs. |
| **Persistence** | In-memory only | This is a test double. Simplicity and zero-dependency startup outweigh durability. State survives the process lifetime only. |
| **Database** | None | A database would add startup complexity and a required external service. The in-memory store with `POST /reset` is sufficient for all test isolation needs. |
| **SWIFT, SFTP, Email adapters** | Not in scope | This mock represents LUSID (the SaaS target), not the WIG source adapters. |

---

## Architecture Design

### Why This Stack

The WIG is Java/Spring Boot. This mock is Python/FastAPI. The reasons:

- **Speed of iteration** — a test double needs to be built and modified quickly as the WIG's integration patterns are clarified
- **Async-native** — FastAPI's ASGI + asyncio makes background task scheduling (virus scan timers, state machine advances) trivial with `asyncio.create_task`
- **Same pattern as bank-ods reference project** — the team already has a running example of the FastAPI + uv + Docker Compose pattern to follow
- **No JVM startup overhead** — the mock starts in under a second

### Layer Separation

```
HTTP Routers  (api/)           — FastAPI routes, HTTP-layer concerns only
     ↓
Service Layer  (services/)     — business logic, no HTTP types
     ↓
In-Memory Stores  (store/)     — state, event log, counters
     ↓
Pydantic Models  (models/)     — data shapes, validation
```

Each layer has a single responsibility. Routers call services only — no direct store access. Services call stores only — no HTTP types. This mirrors the constraint in the WIG's own architecture (no query logic in transport layers).

### Claim-Check Pattern Fidelity

The real LUSID uses a claim-check pattern: payload content goes to Drive, only metadata references go into task fields. The mock reproduces this exactly:

- Drive: stores binary content, returns a file ID
- Workflow: task fields accept `driveFileId`, `driveFilePath` as short strings — no payload body
- The WIG can upload, create a task with the Drive reference, and download results — the exact same code path as against real LUSID

### Async State Machine Design

The task state machine runs as an `asyncio` background task launched at task creation:

```python
asyncio.create_task(store.schedule_auto_advance(
    task_id, processing_delay_s, completion_delay_s, error_rate, on_complete
))
```

This is a deliberate design choice. Alternatives considered:

| Approach | Why Rejected |
|---|---|
| Polling thread that scans all tasks | More complex, requires thread safety, harder to test |
| On-demand advance at GET time | Doesn't mirror LUSID's push model — no natural webhook trigger |
| Celery/background worker | External dependency, overkill for a test double |
| Manual only (no auto-advance) | Fails to test the real async integration pattern — tests would miss timing bugs |

The `asyncio.create_task` approach is simple, requires no threads, and the event loop is the same one serving requests — natural concurrency with no locking needed.

### Virus Scan Simulation

Real LUSID Drive auto-scans every uploaded file and returns `HTTP 423` (Locked) while scanning. This is a documented open item in the WIG architecture (LUSID-006: typical scan latency). The mock simulates this with a configurable delay, enabling tests for:

- Retry-after-delay logic (`HTTP 423`)
- Permanent failure handling (`HTTP 410` — malware)
- Race conditions if the WIG doesn't wait for scan completion before task creation

### Control API Design

The Control API (`/lusid-mock/control/*`) is the test harness interface — not part of the real LUSID API. Key design goals:

- **Reconfigurable at runtime** — `POST /config` changes scan delays, error rates, malware patterns, and webhook URL with no restart. Test scenarios don't need server restarts between cases.
- **Manual advance** — `POST /tasks/{id}/advance` bypasses timers for deterministic in-process tests (using FastAPI's synchronous TestClient where background tasks don't run)
- **Reset** — `POST /reset` clears all state for test isolation without a server restart
- **Event log** — `GET /events` provides a time-sorted audit of everything that happened, enabling tests to assert on the full lifecycle sequence

### Two Test Tiers

A key architectural constraint identified during design: **FastAPI's `TestClient` does not run `asyncio.create_task` background tasks**. The TestClient uses a synchronous ASGI transport that shares no event loop with the background tasks created during request handling.

This means two distinct test tiers are needed:

**In-process tests** (`test_drive.py`, `test_workflow.py`, `test_control.py`, `test_e2e.py`):
- Use `TestClient` — fast, zero external dependencies, ideal for CI
- Cannot test auto-advance; use `POST /advance` for state control
- Test API contracts, error handling, request/response shapes

**Live server tests** (`test_live_server.py`):
- Start a real `uvicorn` instance on port 9001 and a webhook capture server on port 9002
- Issue real HTTP requests via `httpx`
- Poll for state transitions using `_poll_task_state` / `_poll_file_status` helpers
- Test the async state machine, virus scan timers, and real webhook HTTP delivery
- Use short delays (0.3s) via `FAST_CONFIG` — full suite runs in ~24 seconds

This two-tier design gives fast feedback on logic errors (in-process) and confidence that async behavior works end-to-end (live server).

---

## Open Items at Time of Design (Phase 2)

These items from the WIG architecture document were explicitly deferred:

| WIG Item | Impact on Mock |
|---|---|
| LUSID-004: 1:M output modelling | Mock currently returns one result per task. Phase 2: extend `result_fields` to support multiple output file references. |
| LUSID-005: Notification Service webhook subscriptions | Mock uses a static `webhook_url` config. Phase 2: implement `POST /notification/api/webhooks` subscription registration. |
| LUSID-008: Recommended integration pattern for high-volume | Mock has no rate limiting. Phase 2: add configurable rate limit simulation. |
| LUSID-009: Idempotency on task creation | Mock creates a new task for every `POST /workflow/api/tasks`. Phase 2: idempotency key on `correlationId`. |
| WIG-001: Automatic task creation on Drive file upload | Mock does not auto-create tasks on upload. Phase 2: optional config to simulate this. |

---

## What Was Built (Phase 1 Deliverables)

| Component | File(s) | Description |
|---|---|---|
| Pydantic models | `models/drive.py`, `models/workflow.py`, `models/control.py` | Data shapes for files, tasks, config, events |
| Drive store | `store/drive_store.py` | In-memory file dict + scan state + event log |
| Task store | `store/task_store.py` | In-memory task dict + auto-advance coroutine + event log |
| Drive service | `services/drive_service.py` | Upload (schedules scan), get contents (scan state gate), delete |
| Workflow service | `services/workflow_service.py` | Create (schedules auto-advance), get, list |
| Webhook service | `services/webhook_service.py` | Fire webhook POST with configurable failure rate |
| Drive router | `api/drive.py` | `POST/GET/DELETE /drive/api/files` |
| Workflow router | `api/workflow.py` | `POST/GET /workflow/api/tasks` |
| Control router | `api/control.py` | `/lusid-mock/control/*` |
| App factory | `app.py` | Creates FastAPI app with shared state |
| In-process tests | `tests/test_*.py` | 25 tests — contracts, error handling, parity |
| Live server tests | `tests/test_live_server.py` | 15 tests — real async, real webhooks, full pipeline |
| Docker | `Dockerfile`, `docker-compose.yml` | Single-container deployment on port 9000 |
