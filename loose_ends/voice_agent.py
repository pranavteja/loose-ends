"""The hands-free LiveKit agent for Loose Ends.

The voice conversation is deliberately separate from task approval: it can
prepare an editable review draft, but only the existing review screen writes an
approved task to the local board.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    function_tool,
    room_io,
)
from livekit.plugins import groq, silero

from .config import Settings
from .database import Database
from .groq_adapter import GroqAdapter, ProviderError
from .services import LooseEndsService, ServiceError
from .voice_config import VoiceSettings


logger = logging.getLogger("loose_ends.voice")


class ConversationRecorder:
    """Append a private, per-room diagnostic transcript as JSON Lines."""

    def __init__(self, path: Path, room_name: str) -> None:
        self.path = path
        self.room_name = room_name
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "room": self.room_name,
            "event": event_type,
            **payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as transcript_file:
                transcript_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as error:
            # A diagnostic log must never break the live conversation.
            logger.warning("Could not write conversation transcript: %s", error)


def _json_or_text(value: str) -> Any:
    """Decode SDK tool payloads when possible while preserving plain text."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


_DRAFT_REQUEST_PATTERNS = (
    r"\b(?:make|create|prepare)\s+(?:a\s+)?draft\b",
    r"\bdraft\s+(?:it|this|that)\b",
    r"\b(?:try|retry)\s+(?:the\s+)?draft(?:\s+again)?\b",
    r"\b(?:put|send|save|move)\s+(?:it|this|that|the plan)?\s*(?:in|to|for)\s+review\b",
    r"\bready\s+for\s+review\b",
)
_DRAFT_REQUEST_NEGATIONS = (
    r"\bdo\s+not\b",
    r"\bdon't\b",
    r"\bnot\s+yet\b",
    r"\bwait\b",
    r"\bno\s+draft\b",
)
_DRAFT_REVISION_PATTERNS = (
    r"\b(?:actually|instead)\b",
    r"\b(?:change|update|revise|edit|correct|move|add|remove|drop|replace|rename)\b",
    r"\bmake\s+(?:it|that|the\s+date|the\s+first\s+step)\b",
    r"\bset\s+(?:it|that|the\s+date|the\s+time|the\s+deadline)\b",
)
_DRAFT_REVISION_NEGATIONS = (
    r"\bdo\s+not\b",
    r"\bdon't\b",
    r"\bno\s+changes?\b",
    r"\bleave\s+(?:it|that)\b",
    r"\bkeep\s+(?:it|that)\b",
)


def _is_explicit_draft_request(message: str) -> bool:
    """Recognise an affirmative request before allowing a persistence tool."""
    normalised = " ".join(message.casefold().split())
    if any(re.search(pattern, normalised) for pattern in _DRAFT_REQUEST_NEGATIONS):
        return False
    return any(re.search(pattern, normalised) for pattern in _DRAFT_REQUEST_PATTERNS)


def _is_explicit_draft_revision(message: str) -> bool:
    """Recognise a spoken correction that may revise an existing draft."""
    normalised = " ".join(message.casefold().split())
    if any(re.search(pattern, normalised) for pattern in _DRAFT_REVISION_NEGATIONS):
        return False
    return any(re.search(pattern, normalised) for pattern in _DRAFT_REVISION_PATTERNS)


def _planner_service() -> LooseEndsService:
    settings = Settings.from_env()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    return LooseEndsService(database, GroqAdapter(settings), settings)


class PlanningCompanion(Agent):
    """A concise companion that refines spoken thoughts before a user reviews them."""

    def __init__(self, service: LooseEndsService) -> None:
        super().__init__(
            instructions="""
You are Loose Ends, a warm, calm planning companion in a live voice conversation.
Your job is to help the user turn a loose thought into a clear, manageable plan.

Speak naturally and briefly. Ask one focused follow-up at a time only when it
would make the plan materially clearer. Reflect corrections back accurately;
never invent dates, commitments, progress, or reminders. Treat things called
an idea, a maybe, or explicitly not a task as ideas.

Keep each spoken sentence under 180 characters so voice playback begins
quickly and remains within the speech model's per-request limit.

This is an audio-only experience. Never ask the user to type, read a transcript,
or use chat. The user hears your response and can interrupt you at any time.

Keep refining in conversation until the user explicitly asks you to create a
draft, put it in review, or save it for review. At that point call
prepare_review_draft with a compact, complete account of the user's intent,
including the user's answers and any corrections from the whole conversation.
Tell the user the draft is editable and must still be approved on the review
board. Never claim a task was saved or approved.

Once a review draft exists, continue the voice conversation. If the user asks
to change, add, remove, correct, or replace a detail, call revise_review_draft.
Pass the complete corrected plan, including unchanged details from the earlier
conversation—not only the latest correction. Revise the same draft; do not make
another partial draft.

Use read_board only when the user asks about work already on the board. The
board tool is read-only. Do not use tools during the opening greeting.
""".strip()
        )
        self._service = service
        self._draft_requested = False
        self._draft_revision_requested = False
        self._active_capture_id: str | None = None

    def observe_user_turn(self, message: str) -> None:
        """Unlock one draft write only after an explicit affirmative request."""
        if _is_explicit_draft_request(message):
            self._draft_requested = True
        if self._active_capture_id and _is_explicit_draft_revision(message):
            self._draft_revision_requested = True

    async def _persist_review_draft(self, spoken_note: str) -> dict[str, Any]:
        if self._active_capture_id:
            pending = await asyncio.to_thread(self._service.list_review_proposals)
            active_is_pending = any(
                draft["capture_id"] == self._active_capture_id for draft in pending
            )
            if not active_is_pending:
                capture = await asyncio.to_thread(
                    self._service.get_capture, self._active_capture_id
                )
                if capture["state"] != "failed":
                    return {
                        "error": "The active draft is no longer waiting for review.",
                        "instruction": "Do not change approved work. Ask the user to start a new plan instead.",
                        "approval_required": True,
                    }
            result = await asyncio.to_thread(
                self._service.edit_transcript_and_process,
                self._active_capture_id,
                spoken_note,
            )
            action = "retried" if not active_is_pending else "revised"
        else:
            self._active_capture_id = await asyncio.to_thread(
                self._service.create_text_capture,
                spoken_note,
            )
            result = await asyncio.to_thread(
                self._service.process_capture,
                self._active_capture_id,
                0,
            )
            action = "created"

        drafts = await asyncio.to_thread(self._service.list_review_proposals)
        current = [
            draft for draft in drafts if draft["capture_id"] == self._active_capture_id
        ]
        return {
            "summary": result.summary,
            "action": action,
            "draft_count": len(current),
            "drafts": [draft["title"] for draft in current],
            "review_url": "http://127.0.0.1:7861/#review",
            "approval_required": True,
        }

    @function_tool()
    async def prepare_review_draft(self, context: RunContext, spoken_note: str) -> dict[str, Any]:
        """Create editable local review drafts from a user's explicitly confirmed plan.

        Call only after the user has explicitly asked to make a draft or send the
        plan to review. This does not approve a task or make any external change.

        Args:
            spoken_note: A complete, concise restatement of the user's plan,
                including all useful follow-up answers and corrections.
        """
        if not self._draft_requested:
            return {
                "error": "Draft creation is still locked.",
                "instruction": "Keep refining the plan. Ask the user to say 'make a draft' when they are ready.",
                "approval_required": True,
            }

        # Consume the permission before doing any I/O so a repeated tool call in
        # the same turn cannot produce duplicate partial drafts.
        self._draft_requested = False
        context.disallow_interruptions()
        try:
            return await self._persist_review_draft(spoken_note)
        except (ServiceError, ProviderError) as error:
            logger.info("Voice draft creation failed: %s", error)
            return {
                "error": str(error),
                "capture_saved": True,
                "retryable": True,
                "instruction": (
                    "Tell the user the plan is safely kept locally, the draft could not be prepared yet, "
                    "and they can say 'try the draft again'."
                ),
            }

    @function_tool()
    async def revise_review_draft(self, context: RunContext, revised_spoken_note: str) -> dict[str, Any]:
        """Revise the current editable review draft after a spoken correction.

        Call only after a review draft exists and the user explicitly asks to
        change, add, remove, or correct something. This supersedes the earlier
        proposal from the same conversation; it never changes an approved task.

        Args:
            revised_spoken_note: The complete corrected plan, including relevant
                unchanged details and every correction from the conversation.
        """
        if not self._active_capture_id:
            return {
                "error": "There is no active draft to revise.",
                "instruction": "Keep refining verbally, then ask the user to say 'make a draft'.",
                "approval_required": True,
            }
        if not self._draft_revision_requested:
            return {
                "error": "Draft revision is still locked.",
                "instruction": "Only revise after the user explicitly asks for a change.",
                "approval_required": True,
            }

        self._draft_revision_requested = False
        context.disallow_interruptions()
        try:
            return await self._persist_review_draft(revised_spoken_note)
        except (ServiceError, ProviderError) as error:
            logger.info("Voice draft revision failed: %s", error)
            return {
                "error": str(error),
                "draft_preserved": True,
                "retryable": True,
                "instruction": (
                    "Tell the user the existing plan is safe, the revision could not be prepared yet, "
                    "and they can ask to try that change again."
                ),
            }

    @function_tool()
    async def read_board(self, context: RunContext) -> list[dict[str, Any]]:
        """Read the user's locally saved tasks and ideas without changing them.

        Call only when the user asks about saved work, progress, or what is next.
        """
        tasks = await asyncio.to_thread(self._service.list_tasks)
        return [
            {
                "title": task["title"],
                "kind": task["kind"],
                "status": task["status"],
                "due_date": task["due_date"],
                "steps": [
                    {"title": step["title"], "completed": step["completed"]}
                    for step in task["steps"]
                ],
            }
            for task in tasks
        ]


def prewarm(proc: JobProcess) -> None:
    """Load local voice-activity detection once so first response feels immediate."""
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=VoiceSettings.from_env().agent_name)
async def voice_entrypoint(ctx: JobContext) -> None:
    voice = VoiceSettings.from_env()
    settings = Settings.from_env()
    settings.ensure_directories()
    safe_room_name = re.sub(r"[^A-Za-z0-9._-]", "_", ctx.room.name)
    recorder = ConversationRecorder(
        settings.data_dir / "logs" / "conversations" / f"{safe_room_name}.jsonl",
        ctx.room.name,
    )
    recorder.append("session_started")
    service = _planner_service()
    session = AgentSession(
        # Groq Whisper is final-segment transcription. VAD supplies natural
        # hands-free turn detection, and Groq Orpheus publishes assistant audio
        # directly into the LiveKit room for reliable playback and interruption.
        stt=groq.STT(model=voice.stt_model, language=voice.stt_language),
        llm=groq.LLM(model=voice.llm_model),
        tts=groq.TTS(model=voice.tts_model, voice=voice.tts_voice),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    companion = PlanningCompanion(service)

    @session.on("user_input_transcribed")
    def log_transcript(event: Any) -> None:
        if event.is_final:
            logger.info(
                "Voice turn transcribed (%s, %d characters)",
                event.language or "und",
                len(event.transcript),
            )
            companion.observe_user_turn(event.transcript)

    @session.on("conversation_item_added")
    def record_conversation_item(event: Any) -> None:
        item = event.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None)
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            recorder.append(
                "message",
                role=role,
                text=text.strip(),
                item_id=getattr(item, "id", None),
                interrupted=bool(getattr(item, "interrupted", False)),
            )

    @session.on("function_tools_executed")
    def record_function_tools(event: Any) -> None:
        for call, output in event.zipped():
            recorder.append(
                "tool",
                name=call.name,
                call_id=call.call_id,
                arguments=_json_or_text(call.arguments),
                output=_json_or_text(output.output),
                is_error=output.is_error,
            )

    @session.on("speech_created")
    def record_speech_created(event: Any) -> None:
        recorder.append(
            "speech_created",
            speech_id=event.speech_handle.id,
            source=event.source,
            user_initiated=event.user_initiated,
        )

    await session.start(
        agent=companion,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_output=True,
            text_output=room_io.TextOutputOptions(sync_transcription=False),
        ),
    )
    await ctx.connect()
    await session.generate_reply(
        instructions=(
            "Welcome the user in one short sentence. Invite them to tell you what is on their mind, "
            "and mention they can interrupt you at any time."
        ),
        allow_interruptions=True,
    )


def run() -> None:
    """Run as ``python -m loose_ends.voice_agent dev`` or ``start``."""
    agents.cli.run_app(server)


if __name__ == "__main__":
    run()
