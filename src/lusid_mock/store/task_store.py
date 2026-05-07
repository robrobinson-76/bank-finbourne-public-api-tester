from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from lusid_mock.models.workflow import Task, TaskState
from lusid_mock.models.control import EventEntry


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._events: list[EventEntry] = []
        self._webhook_fired: int = 0
        self._webhook_failed: int = 0
        self._on_complete: Callable[[Task], Any] | None = None  # webhook callback

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _log(self, event_type: str, entity_id: str, detail: str) -> None:
        self._events.append(EventEntry(
            timestamp=self._now(),
            event_type=event_type,
            entity_id=entity_id,
            detail=detail,
        ))

    def create(
        self,
        correlation_id: str,
        source_channel: str,
        drive_file_path: str,
        drive_file_id: str,
        payload_type: str | None,
        fields: dict[str, str],
    ) -> Task:
        task_id = str(uuid.uuid4())
        now = self._now()
        task = Task(
            id=task_id,
            state=TaskState.PENDING,
            correlationId=correlation_id,
            sourceChannel=source_channel,
            driveFilePath=drive_file_path,
            driveFileId=drive_file_id,
            payloadType=payload_type,
            fields=fields,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = task
        self._log("TASK_CREATED", task_id, f"correlationId={correlation_id} state=Pending")
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list(self, state_filter: str | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if state_filter:
            tasks = [t for t in tasks if t.state.value == state_filter]
        return tasks

    def advance(self, task_id: str, new_state: TaskState, result_fields: dict | None = None) -> Task | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        now = self._now()
        update: dict[str, Any] = {"state": new_state, "updated_at": now}
        if result_fields:
            update["result_fields"] = result_fields
        if new_state in (TaskState.COMPLETE, TaskState.ERROR):
            update["completed_at"] = now
        updated = task.model_copy(update=update)
        self._tasks[task_id] = updated
        self._log("TASK_STATE_CHANGED", task_id, f"state={new_state.value}")
        return updated

    def counts(self) -> dict[str, int]:
        states = [t.state for t in self._tasks.values()]
        return {
            "pending": states.count(TaskState.PENDING),
            "processing": states.count(TaskState.PROCESSING),
            "complete": states.count(TaskState.COMPLETE),
            "error": states.count(TaskState.ERROR),
        }

    def record_webhook(self, *, success: bool) -> None:
        if success:
            self._webhook_fired += 1
        else:
            self._webhook_failed += 1

    def reset(self) -> None:
        self._tasks.clear()
        self._webhook_fired = 0
        self._webhook_failed = 0
        self._log("STORE_RESET", "tasks", "all tasks cleared")

    def all_events(self, drive_events: list[EventEntry]) -> list[EventEntry]:
        combined = self._events + drive_events
        return sorted(combined, key=lambda e: e.timestamp)

    async def schedule_auto_advance(
        self,
        task_id: str,
        processing_delay_s: float,
        completion_delay_s: float,
        error_rate: float,
        on_complete: Callable[[Task], Any] | None,
    ) -> None:
        import random
        await asyncio.sleep(processing_delay_s)
        self.advance(task_id, TaskState.PROCESSING)

        await asyncio.sleep(completion_delay_s)
        final_state = TaskState.ERROR if random.random() < error_rate else TaskState.COMPLETE
        task = self.advance(task_id, final_state)

        if task and final_state == TaskState.COMPLETE and on_complete:
            await on_complete(task)
