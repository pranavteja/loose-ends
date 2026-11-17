"""The hands-free LiveKit agent for Loose Ends.

The voice conversation is deliberately separate from task approval: it can
prepare an editable review draft, but only the existing review screen writes an
approved task to the local board.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
from .groq_adapter import GroqAdapter
from .services import LooseEndsService, ServiceError
from .voice_config import VoiceSettings


logger = logging.getLogger("loose_ends.voice")


_DRAFT_REQUEST_PATTERNS = (
    r"\b(?:make|create|prepare)\s+(?:a\s+)?draft\b",
    r"\bdraft\s+(?:it|this|that)\b",
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


def _is_explicit_draft_request(message: str) -> bool:
    """Recognise an affirmative request before allowing a persistence tool."""
    normalised = " ".join(message.casefold().split())
    if any(re.search(pattern, normalised) for pattern in _DRAFT_REQUEST_NEGATIONS):
        return False
    return any(re.search(pattern, normalised) for pattern in _DRAFT_REQUEST_PATTERNS)


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

Keep refining in conversation until the user explicitly asks you to create a
draft, put it in review, or save it for review. At that point call
prepare_review_draft with a compact, complete account of the user's intent,
including the user's answers and any corrections from the whole conversation.
Tell the user the draft is editable and must still be approved on the review
board. Never claim a task was saved or approved.

Use read_board only when the user asks about work already on the board. The
board tool is read-only. Do not use tools during the opening greeting.
""".strip()
        )
        self._service = service
        self._draft_requested = False

    def observe_user_turn(self, message: str) -> None:
        """Unlock one draft write only after an explicit affirmative request."""
        if _is_explicit_draft_request(message):
            self._draft_requested = True

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
            capture_id = await asyncio.to_thread(self._service.create_text_capture, spoken_note)
            result = await asyncio.to_thread(self._service.process_capture, capture_id, 0)
            drafts = await asyncio.to_thread(self._service.list_review_proposals)
            created = [draft for draft in drafts if draft["capture_id"] == capture_id]
            return {
                "summary": result.summary,
                "draft_count": len(created),
                "drafts": [draft["title"] for draft in created],
                "review_url": "http://127.0.0.1:7861/",
                "approval_required": True,
            }
        except ServiceError as error:
            logger.info("Voice draft creation failed: %s", error)
            return {"error": str(error), "capture_saved": True}

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
    service = _planner_service()
    session = AgentSession(
        # Groq Whisper is final-segment transcription. VAD supplies natural
        # hands-free turn detection. Assistant text is sent through LiveKit and
        # spoken by the browser, avoiding a separate cloud TTS dependency.
        stt=groq.STT(model=voice.stt_model, language=voice.stt_language),
        llm=groq.LLM(model=voice.llm_model),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    companion = PlanningCompanion(service)

    @session.on("user_input_transcribed")
    def log_transcript(event: Any) -> None:
        if event.is_final:
            logger.info("Voice turn transcribed (%s): %s", event.language or "und", event.transcript)
            companion.observe_user_turn(event.transcript)

    async def handle_text_input(active_session: AgentSession, event: room_io.TextInputEvent) -> None:
        """Route typed messages through the same agent and conversation history."""
        message = event.text.strip()
        if not message:
            return
        logger.info("Typed turn received: %s", message)
        companion.observe_user_turn(message)
        try:
            await active_session.interrupt()
        except RuntimeError:
            # There may be no speech to interrupt; the typed turn is still valid.
            pass
        active_session.generate_reply(user_input=message, allow_interruptions=True)

    await session.start(
        agent=companion,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            text_input=room_io.TextInputOptions(text_input_cb=handle_text_input),
            audio_output=False,
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
