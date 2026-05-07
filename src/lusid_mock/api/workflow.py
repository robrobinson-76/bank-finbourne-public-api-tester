from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException, Query

from lusid_mock.models.workflow import TaskCreateRequest, Task, TaskListResponse
from lusid_mock.services import workflow_service

router = APIRouter(prefix="/workflow/api/tasks", tags=["workflow"])


@router.post("", status_code=201, response_model=Task)
async def create_task(req: TaskCreateRequest, request: Request):
    return await workflow_service.create_task(
        store=request.app.state.task_store,
        config=request.app.state.config,
        req=req,
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    request: Request,
    state: str | None = Query(default=None, description="Filter by state: Pending, Processing, Complete, Error"),
):
    tasks = workflow_service.list_tasks(request.app.state.task_store, state)
    return TaskListResponse(values=tasks, total_count=len(tasks))


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str, request: Request):
    task = workflow_service.get_task(request.app.state.task_store, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
