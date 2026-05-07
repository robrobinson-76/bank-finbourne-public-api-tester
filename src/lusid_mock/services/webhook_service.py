from __future__ import annotations
import asyncio
import random

import httpx

from lusid_mock.models.workflow import Task
from lusid_mock.models.control import ScenarioConfig
from lusid_mock.store.task_store import TaskStore


async def fire_webhook(task: Task, config: ScenarioConfig, task_store: TaskStore) -> None:
    if not config.webhook_url:
        return
    if random.random() < config.webhook_failure_rate:
        task_store.record_webhook(success=False)
        task_store._log("WEBHOOK_FAILED", task.id, f"simulated failure url={config.webhook_url}")
        return

    payload = {
        "task_id": task.id,
        "correlation_id": task.correlationId,
        "state": task.state.value,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "result_fields": task.result_fields,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(config.webhook_url, json=payload)
        success = resp.is_success
    except Exception:
        success = False

    task_store.record_webhook(success=success)
    status = "fired" if success else "failed"
    task_store._log("WEBHOOK_FIRED", task.id, f"status={status} url={config.webhook_url}")
