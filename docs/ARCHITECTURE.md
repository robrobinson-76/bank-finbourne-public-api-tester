# LUSID Mock Server — Architecture

## Purpose

This server is a test double for the FINBOURNE LUSID API. Applications that use LUSID (Drive, Workflow, Notification) can point at this mock during development and CI without requiring real credentials, network access, or a FINBOURNE subscription.

The primary consumer is the Workflow Integration Gateway (WIG), which uploads payloads to LUSID Drive, creates Workflow tasks, and listens for completion webhooks. This mock lets the full WIG pipeline run locally.

---

## Layers

```text
HTTP clients (WIG, tests, curl)
        ↓
   FastAPI Routers  (api/)
   /drive  /workflow  /lusid-mock/control
        ↓
   Service Layer  (services/)
   drive_service  workflow_service  webhook_service
        ↓
   In-Memory Stores  (store/)
   DriveStore  TaskStore (+ shared event log)
        ↓
   Pydantic Models  (models/)
   DriveFile  Task  ScenarioConfig  EventEntry
```

No database. All state lives in Python dicts on `app.state`. State resets on restart or via `POST /lusid-mock/control/reset`.

---

## Drive Store

`DriveStore` holds files as `dict[file_id, DriveFile]`. Each file carries its binary content, path, content type, and scan state (`SCANNING | CLEAN | MALWARE`).

On upload, the store immediately marks the file `SCANNING` and schedules an async task (`asyncio.create_task`) that sleeps for `virus_scan_delay_s` then transitions the file to `CLEAN` or `MALWARE` based on `malware_path_patterns`.

GET /contents returns:

- `HTTP 423` while `SCANNING`
- `HTTP 410` if `MALWARE`
- `HTTP 200 + content` if `CLEAN`

---

## Task Store and State Machine

`TaskStore` holds tasks as `dict[task_id, Task]`. Tasks are immutable Pydantic models replaced on each state transition via `model_copy`.

On task creation, `workflow_service.create_task` schedules an async background coroutine that drives the state machine:

```text
Pending  →(processing_delay_s)→  Processing  →(completion_delay_s)→  Complete
                                                                    ↘  Error (if random() < error_rate)
```

The Control API's `/advance` endpoint lets tests bypass the timers and force any state transition immediately.

On reaching `Complete`, the webhook service fires a POST to `config.webhook_url` (if set).

---

## Scenario Config

All timing and behavior is driven by `ScenarioConfig`, held on `app.state.config` and updatable via `POST /lusid-mock/control/config` without a restart.

| Field | Default | Effect |
|---|---|---|
| `virus_scan_delay_s` | 2.0 | Seconds before SCANNING → CLEAN/MALWARE |
| `processing_delay_s` | 3.0 | Seconds before Pending → Processing |
| `completion_delay_s` | 5.0 | Seconds before Processing → Complete/Error |
| `error_rate` | 0.0 | Probability (0–1) a task ends in Error |
| `malware_path_patterns` | [] | fnmatch patterns — matching file paths → MALWARE |
| `webhook_url` | None | POST target for task completion events |
| `webhook_failure_rate` | 0.0 | Probability (0–1) webhook delivery is simulated as failed |

For fast unit tests, set all delays to 0 and use the `/advance` endpoint to control state explicitly.

---

## Event Log

Every significant action appends an `EventEntry` to the store's internal list. The Control API's `GET /lusid-mock/control/events` returns the combined, time-sorted log from both stores. Event types:

- `FILE_UPLOADED`, `FILE_DELETED`, `FILE_SCAN_STATE`
- `TASK_CREATED`, `TASK_STATE_CHANGED`
- `WEBHOOK_FIRED`, `WEBHOOK_FAILED`
- `STORE_RESET`

This is the monitoring output used to verify end-to-end flows in tests and during manual exploration.

---

## Adding New LUSID Surfaces (Phase 2)

To mock additional LUSID API surfaces:

1. Add Pydantic models to `models/`
2. Add a store in `store/` (or extend an existing one)
3. Add a service module in `services/`
4. Add a FastAPI router in `api/` and register it in `app.py`
5. Add tests

The pattern is identical for each surface. No framework changes needed.

---

## Design Decisions

**In-memory only** — no database. This is a test double, not a durable service. Simplicity and zero-dependency startup are the priority. State survives only the process lifetime.

**Auto-advance via asyncio background tasks** — mirrors the real LUSID behavior (task processing happens asynchronously after creation). Tests that need deterministic control use the `/advance` endpoint instead.

**ScenarioConfig on app.state** — allows test scenarios to reconfigure behavior (delays, error rates, malware patterns, webhook URL) between test cases via HTTP, with no server restart. This makes the mock usable from any test framework, not just pytest.

**FastAPI TestClient for tests** — synchronous test client, no real HTTP stack needed. Background async tasks are not waited on in tests; instead tests use the `/advance` endpoint for explicit state control.
