from __future__ import annotations
from fastapi import FastAPI

from lusid_mock.models.control import ScenarioConfig
from lusid_mock.store.drive_store import DriveStore
from lusid_mock.store.task_store import TaskStore
from lusid_mock.api import drive, workflow, control


def create_app() -> FastAPI:
    app = FastAPI(
        title="LUSID Mock Server",
        description="In-memory mock of FINBOURNE LUSID Drive, Workflow, and Notification APIs for local testing.",
        version="0.1.0",
    )

    app.state.drive_store = DriveStore()
    app.state.task_store = TaskStore()
    app.state.config = ScenarioConfig()

    app.include_router(drive.router)
    app.include_router(workflow.router)
    app.include_router(control.router)

    return app


app = create_app()
