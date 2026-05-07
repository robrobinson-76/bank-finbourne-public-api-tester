from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException

from lusid_mock.models.control import ScenarioConfig, StatusResponse, AdvanceRequest, EventEntry
from lusid_mock.services import workflow_service

router = APIRouter(prefix="/lusid-mock/control", tags=["control"])


@router.get("/status", response_model=StatusResponse)
async def status(request: Request):
    ds = request.app.state.drive_store
    ts = request.app.state.task_store
    dc = ds.counts()
    tc = ts.counts()
    return StatusResponse(
        files_total=dc["total"],
        files_scanning=dc["scanning"],
        files_clean=dc["clean"],
        files_malware=dc["malware"],
        tasks_pending=tc["pending"],
        tasks_processing=tc["processing"],
        tasks_complete=tc["complete"],
        tasks_error=tc["error"],
        webhooks_fired=ts._webhook_fired,
        webhooks_failed=ts._webhook_failed,
        config=request.app.state.config,
    )


@router.get("/events", response_model=list[EventEntry])
async def events(request: Request):
    ts = request.app.state.task_store
    ds = request.app.state.drive_store
    return ts.all_events(ds._events)


@router.post("/config", response_model=ScenarioConfig)
async def update_config(cfg: ScenarioConfig, request: Request):
    request.app.state.config = cfg
    return cfg


@router.post("/tasks/{task_id}/advance")
async def advance_task(task_id: str, body: AdvanceRequest, request: Request):
    task = workflow_service.advance_task(
        store=request.app.state.task_store,
        task_id=task_id,
        target_state=body.target_state,
        result_fields=body.result_fields,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found or invalid state")
    return task


@router.post("/reset", status_code=204)
async def reset(request: Request):
    request.app.state.drive_store.reset()
    request.app.state.task_store.reset()
    request.app.state.config = ScenarioConfig()
