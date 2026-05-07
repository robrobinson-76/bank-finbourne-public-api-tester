from __future__ import annotations
import asyncio

from lusid_mock.models.workflow import Task, TaskCreateRequest, TaskState
from lusid_mock.models.control import ScenarioConfig
from lusid_mock.store.task_store import TaskStore
from lusid_mock.services.webhook_service import fire_webhook


async def create_task(
    store: TaskStore,
    config: ScenarioConfig,
    req: TaskCreateRequest,
) -> Task:
    task = store.create(
        correlation_id=req.correlationId,
        source_channel=req.sourceChannel,
        drive_file_path=req.driveFilePath,
        drive_file_id=req.driveFileId,
        payload_type=req.payloadType,
        fields=req.fields,
    )

    async def on_complete(t: Task) -> None:
        await fire_webhook(t, config, store)

    asyncio.create_task(store.schedule_auto_advance(
        task_id=task.id,
        processing_delay_s=config.processing_delay_s,
        completion_delay_s=config.completion_delay_s,
        error_rate=config.error_rate,
        on_complete=on_complete,
    ))
    return task


def get_task(store: TaskStore, task_id: str) -> Task | None:
    return store.get(task_id)


def list_tasks(store: TaskStore, state_filter: str | None) -> list[Task]:
    return store.list(state_filter)


def advance_task(
    store: TaskStore,
    task_id: str,
    target_state: str,
    result_fields: dict,
) -> Task | None:
    try:
        state = TaskState(target_state)
    except ValueError:
        return None
    return store.advance(task_id, state, result_fields or None)
