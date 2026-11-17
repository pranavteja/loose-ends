"""Unified local API and static server for the Loose Ends interface.

This process never sends the LiveKit API secret to the browser. It listens on
loopback by default, appropriate for the single-user local version of Loose Ends.
The voice conversation, draft review, and task board share one origin so the
user never has to move between an embedded page and a separate application.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration
from pydantic import BaseModel, Field

from loose_ends.config import PROJECT_ROOT, Settings
from loose_ends.database import Database
from loose_ends.groq_adapter import GroqAdapter
from loose_ends.services import ConflictError, LooseEndsService, NotFoundError, ServiceError
from loose_ends.voice_config import VoiceSettings


DIST_DIR = PROJECT_ROOT / "voice-ui" / "dist"
ASSETS_DIR = DIST_DIR / "assets"
voice_settings = VoiceSettings.from_env()
app_settings = Settings.from_env()
app_settings.ensure_directories()
database = Database(app_settings.database_path)
database.initialize()
service = LooseEndsService(database, GroqAdapter(app_settings), app_settings)
app = FastAPI(title="Loose Ends", docs_url=None, redoc_url=None)


class TokenRequest(BaseModel):
    """No user-supplied identity is accepted: each local session is opaque."""

    room_name: str | None = None


class ProposalEdits(BaseModel):
    title: str
    description: str = ""
    due_date: str | None = None
    work_start_at: str | None = None
    steps: list[str] = Field(default_factory=list)


class TaskStatusRequest(BaseModel):
    status: str


class StepStatusRequest(BaseModel):
    completed: bool


def _missing_voice_values() -> list[str]:
    missing = voice_settings.missing_livekit_values()
    if not os.getenv("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    return missing


def _credentials_or_error() -> tuple[str, str, str]:
    missing = _missing_voice_values()
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Voice setup is incomplete.",
                "missing": missing,
                "hint": "Copy the LiveKit values into .env, then restart the local voice server.",
            },
        )
    return (
        voice_settings.livekit_url or "",
        voice_settings.livekit_api_key or "",
        voice_settings.livekit_api_secret or "",
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ready": not _missing_voice_values(),
        "missing": _missing_voice_values(),
        "agent_name": voice_settings.agent_name,
    }


@app.post("/api/token", status_code=201)
def create_token(request: TokenRequest) -> dict[str, str]:
    livekit_url, api_key, api_secret = _credentials_or_error()
    # Ignore arbitrary names in the public client. Keeping this opaque avoids
    # placing a person's name in LiveKit room logs.
    room_name = request.room_name or f"loose-ends-{uuid.uuid4().hex}"
    identity = f"local-{uuid.uuid4().hex}"
    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("Local user")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_room_config(
            RoomConfiguration(
                agents=[RoomAgentDispatch(agent_name=voice_settings.agent_name)],
            )
        )
        .to_jwt()
    )
    return {"server_url": livekit_url, "participant_token": token}


def _service_error(error: ServiceError) -> HTTPException:
    if isinstance(error, NotFoundError):
        status_code = 404
    elif isinstance(error, ConflictError):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=str(error))


@app.get("/api/review")
def list_review_proposals() -> dict[str, object]:
    return {"proposals": service.list_review_proposals()}


@app.post("/api/review/{proposal_id}/approve")
def approve_proposal(proposal_id: str, edits: ProposalEdits) -> dict[str, object]:
    try:
        task = service.approve_proposal(proposal_id, edits.model_dump())
    except ServiceError as error:
        raise _service_error(error) from error
    return {"task": task}


@app.post("/api/review/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: str) -> dict[str, bool]:
    try:
        service.dismiss_proposal(proposal_id)
    except ServiceError as error:
        raise _service_error(error) from error
    return {"dismissed": True}


@app.get("/api/board")
def list_tasks() -> dict[str, object]:
    return {"tasks": service.list_tasks()}


@app.patch("/api/tasks/{task_id}/status")
def update_task_status(task_id: str, request: TaskStatusRequest) -> dict[str, object]:
    try:
        task = service.set_task_status(task_id, request.status)
    except ServiceError as error:
        raise _service_error(error) from error
    return {"task": task}


@app.patch("/api/steps/{step_id}")
def update_step(step_id: str, request: StepStatusRequest) -> dict[str, object]:
    try:
        task = service.set_step_completed(step_id, request.completed)
    except ServiceError as error:
        raise _service_error(error) from error
    return {"task": task}


if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
def voice_home() -> FileResponse:
    if not (DIST_DIR / "index.html").is_file():
        raise HTTPException(
            status_code=503,
            detail="The voice interface has not been built. Run npm install then npm run build in voice-ui.",
        )
    return FileResponse(DIST_DIR / "index.html")


@app.get("/{asset_path:path}")
def voice_asset(asset_path: str) -> FileResponse:
    requested = (DIST_DIR / asset_path).resolve()
    if DIST_DIR.resolve() in requested.parents and requested.is_file():
        return FileResponse(requested)
    return voice_home()


def main() -> None:
    uvicorn.run(app, host=app_settings.host, port=app_settings.port, log_level=os.getenv("LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
