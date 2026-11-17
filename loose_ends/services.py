"""Application services: persistence, revision guards, and explicit approval rules."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .database import Database
from .groq_adapter import ProviderError


LOCAL_OWNER = "local-user"


class Planner(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...

    def propose_plan(
        self, transcript: str, replies: list[dict[str, str]], captured_at: str, timezone: str, question_budget: int
    ) -> dict[str, Any]: ...

    def answer_about_tasks(self, message: str, task_context: list[dict[str, Any]]) -> str: ...


class ServiceError(RuntimeError):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    capture_id: str
    transcript: str
    summary: str
    question: str | None
    proposals_created: int


class LooseEndsService:
    def __init__(self, database: Database, planner: Planner, settings: Settings) -> None:
        self.database = database
        self.planner = planner
        self.settings = settings
        try:
            self._timezone = ZoneInfo(settings.timezone)
        except ZoneInfoNotFoundError:
            self._timezone = ZoneInfo("UTC")

    def create_text_capture(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ServiceError("Type a thought before creating a plan.")
        if len(text) > 10_000:
            raise ServiceError("Keep a capture under 10,000 characters.")
        return self._create_capture("text", original_text=text, transcript=text, audio_path=None)

    def create_audio_capture(self, temporary_audio_path: str) -> str:
        source = Path(temporary_audio_path)
        if not source.is_file():
            raise ServiceError("The recording could not be read. Please record again or type the note.")
        if source.stat().st_size > self.settings.max_audio_bytes:
            raise ServiceError("That recording is over the configured 25 MB free-tier limit. Please make it shorter.")
        capture_id = str(uuid.uuid4())
        suffix = source.suffix.lower() or ".webm"
        destination = self.settings.audio_dir / f"{capture_id}{suffix}"
        try:
            shutil.copy2(source, destination)
        except OSError as error:
            raise ServiceError("The recording could not be saved locally. Please retry or type the note.") from error
        try:
            return self._create_capture("audio", original_text=None, transcript=None, audio_path=str(destination), capture_id=capture_id)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def _create_capture(
        self, input_type: str, original_text: str | None, transcript: str | None, audio_path: str | None, capture_id: str | None = None
    ) -> str:
        capture_id = capture_id or str(uuid.uuid4())
        now = self._now()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO captures (id, owner_id, input_type, original_text, transcript, audio_path, captured_at,
                timezone, revision, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'saved', ?, ?)""",
                (capture_id, LOCAL_OWNER, input_type, original_text, transcript, audio_path, now, self.settings.timezone, now, now),
            )
        return capture_id

    def process_capture(self, capture_id: str, question_budget: int = 1) -> ProcessingResult:
        capture = self.get_capture(capture_id)
        attempt_id = str(uuid.uuid4())
        now = self._now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE captures SET state = 'processing', attempt_id = ?, error_message = NULL, updated_at = ? WHERE id = ?",
                (attempt_id, now, capture_id),
            )
        try:
            transcript = capture["transcript"]
            if not transcript:
                audio_path = capture["audio_path"]
                if not audio_path:
                    raise ServiceError("This capture has neither text nor audio.")
                transcript = self.planner.transcribe(Path(audio_path))
                with self.database.connect() as connection:
                    connection.execute(
                        "UPDATE captures SET transcript = ?, updated_at = ? WHERE id = ? AND attempt_id = ?",
                        (transcript, self._now(), capture_id, attempt_id),
                    )
            replies = self._clarification_replies(capture_id, int(capture["revision"]))
            existing_questions = self._clarification_count(capture_id, int(capture["revision"]))
            allowed_question_budget = max(0, min(question_budget, 1)) if existing_questions < 2 else 0
            plan = self.planner.propose_plan(
                transcript=transcript,
                replies=replies,
                captured_at=capture["captured_at"],
                timezone=capture["timezone"],
                question_budget=allowed_question_budget,
            )
            self._save_plan(capture_id, int(capture["revision"]), attempt_id, plan)
            return ProcessingResult(capture_id, transcript, plan["summary"], plan["question"], len(plan["proposals"]))
        except (ProviderError, ServiceError) as error:
            self._mark_processing_failed(capture_id, attempt_id, str(error))
            raise
        except Exception as error:
            self._mark_processing_failed(capture_id, attempt_id, "Processing failed. Your capture is saved; please retry.")
            raise ServiceError("Processing failed. Your capture is saved; please retry.") from error

    def retry_capture(self, capture_id: str) -> ProcessingResult:
        return self.process_capture(capture_id, question_budget=1)

    def edit_transcript_and_process(self, capture_id: str, text: str) -> ProcessingResult:
        text = text.strip()
        if not text:
            raise ServiceError("The transcript cannot be empty.")
        if len(text) > 10_000:
            raise ServiceError("Keep the transcript under 10,000 characters.")
        now = self._now()
        with self.database.connect() as connection:
            capture = connection.execute("SELECT revision FROM captures WHERE id = ? AND owner_id = ?", (capture_id, LOCAL_OWNER)).fetchone()
            if capture is None:
                raise NotFoundError("That capture no longer exists.")
            connection.execute(
                "UPDATE captures SET transcript = ?, revision = ?, state = 'saved', error_message = NULL, updated_at = ? WHERE id = ?",
                (text, int(capture["revision"]) + 1, now, capture_id),
            )
            connection.execute("UPDATE proposals SET state = 'superseded', updated_at = ? WHERE capture_id = ? AND state = 'draft'", (now, capture_id))
        return self.process_capture(capture_id, question_budget=1)

    def answer_clarification(self, capture_id: str, answer: str, *, skip: bool = False, fewer_questions: bool = False) -> ProcessingResult:
        answer = answer.strip()
        if not skip and not fewer_questions and not answer:
            raise ServiceError("Answer the question, or choose Skip.")
        now = self._now()
        with self.database.connect() as connection:
            capture = connection.execute("SELECT revision FROM captures WHERE id = ? AND owner_id = ?", (capture_id, LOCAL_OWNER)).fetchone()
            if capture is None:
                raise NotFoundError("That capture no longer exists.")
            clarification = connection.execute(
                """SELECT id FROM clarifications WHERE capture_id = ? AND revision = ? AND answer IS NULL
                ORDER BY created_at DESC LIMIT 1""",
                (capture_id, capture["revision"]),
            ).fetchone()
            if clarification is None:
                raise ConflictError("There is no pending clarification for this capture. Retry or open its draft instead.")
            connection.execute(
                "UPDATE clarifications SET answer = ?, skipped = ?, answered_at = ? WHERE id = ?",
                (None if (skip or fewer_questions) else answer, int(skip or fewer_questions), now, clarification["id"]),
            )
        return self.process_capture(capture_id, question_budget=0 if (skip or fewer_questions) else 1)

    def _save_plan(self, capture_id: str, revision: int, attempt_id: str, plan: dict[str, Any]) -> None:
        now = self._now()
        with self.database.connect() as connection:
            current = connection.execute("SELECT revision, attempt_id FROM captures WHERE id = ?", (capture_id,)).fetchone()
            if current is None:
                raise NotFoundError("This capture was deleted while processing.")
            if int(current["revision"]) != revision or current["attempt_id"] != attempt_id:
                raise ConflictError("A newer version of this capture exists. Reload it before reviewing the plan.")
            connection.execute("UPDATE proposals SET state = 'superseded', updated_at = ? WHERE capture_id = ? AND revision = ? AND state = 'draft'", (now, capture_id, revision))
            for proposal in plan["proposals"]:
                connection.execute(
                    """INSERT INTO proposals (id, capture_id, revision, kind, title, description, source_excerpt,
                    timing_phrase, due_date, work_start_at, timezone, needs_clarification, missing_detail,
                    proposed_steps_json, state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
                    (
                        str(uuid.uuid4()), capture_id, revision, proposal["kind"], proposal["title"], proposal["description"],
                        proposal["source_excerpt"], proposal["timing_phrase"], proposal["due_date"], proposal["work_start_at"],
                        self.settings.timezone, int(proposal["needs_clarification"]), proposal["missing_detail"],
                        json.dumps(proposal["suggested_steps"], ensure_ascii=False), now, now,
                    ),
                )
            if plan["question"]:
                connection.execute(
                    "INSERT INTO clarifications (id, capture_id, revision, question, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), capture_id, revision, plan["question"], now),
                )
            connection.execute(
                "UPDATE captures SET state = ?, error_message = NULL, updated_at = ? WHERE id = ? AND attempt_id = ?",
                ("needs_clarification" if plan["question"] else "ready", now, capture_id, attempt_id),
            )

    def _mark_processing_failed(self, capture_id: str, attempt_id: str, message: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE captures SET state = 'failed', error_message = ?, updated_at = ? WHERE id = ? AND attempt_id = ?",
                (message[:500], self._now(), capture_id, attempt_id),
            )

    def get_capture(self, capture_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM captures WHERE id = ? AND owner_id = ?", (capture_id, LOCAL_OWNER)).fetchone()
        if row is None:
            raise NotFoundError("Capture not found.")
        return dict(row)

    def list_review_proposals(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT p.* FROM proposals p JOIN captures c ON c.id = p.capture_id
                WHERE c.owner_id = ? AND p.state = 'draft' ORDER BY p.created_at DESC""",
                (LOCAL_OWNER,),
            ).fetchall()
        return [self._proposal_dict(row) for row in rows]

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.* FROM proposals p JOIN captures c ON c.id = p.capture_id
                WHERE p.id = ? AND c.owner_id = ?""",
                (proposal_id, LOCAL_OWNER),
            ).fetchone()
        if row is None:
            raise NotFoundError("Proposal not found.")
        return self._proposal_dict(row)

    def _proposal_dict(self, row: Any) -> dict[str, Any]:
        proposal = dict(row)
        proposal["suggested_steps"] = json.loads(proposal.pop("proposed_steps_json"))
        proposal["needs_clarification"] = bool(proposal["needs_clarification"])
        return proposal

    def approve_proposal(self, proposal_id: str, edits: dict[str, Any], request_key: str | None = None) -> dict[str, Any]:
        now = self._now()
        request_key = request_key or f"approval:{proposal_id}"
        with self.database.connect() as connection:
            proposal_row = connection.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if proposal_row is None:
                raise NotFoundError("Proposal not found.")
            proposal = self._proposal_dict(proposal_row)
            existing = connection.execute("SELECT * FROM tasks WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if existing is not None:
                return self._task_dict(connection, existing)
            if proposal["state"] != "draft":
                raise ConflictError("This proposal is no longer available for approval. Refresh the review list.")

            task_values = self._validate_edits(proposal, edits)
            payload_hash = self._payload_hash(task_values)
            receipt = connection.execute(
                "SELECT * FROM request_receipts WHERE owner_id = ? AND operation = 'approve_proposal' AND request_key = ?",
                (LOCAL_OWNER, request_key),
            ).fetchone()
            if receipt is not None:
                if receipt["payload_hash"] != payload_hash:
                    raise ConflictError("This approval key was reused with different edits. Reload the proposal and try again.")
                task = connection.execute("SELECT * FROM tasks WHERE id = ?", (receipt["result_id"],)).fetchone()
                if task is not None:
                    return self._task_dict(connection, task)

            task_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO tasks (id, owner_id, proposal_id, source_capture_id, source_excerpt, kind, title,
                description, due_date, work_start_at, timezone, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (task_id, LOCAL_OWNER, proposal_id, proposal["capture_id"], proposal["source_excerpt"], proposal["kind"],
                 task_values["title"], task_values["description"], task_values["due_date"], task_values["work_start_at"],
                 proposal["timezone"], now, now),
            )
            for position, step in enumerate(task_values["steps"], start=1):
                connection.execute(
                    "INSERT INTO steps (id, task_id, position, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), task_id, position, step, now, now),
                )
            connection.execute("UPDATE proposals SET state = 'approved', updated_at = ? WHERE id = ?", (now, proposal_id))
            connection.execute(
                """INSERT INTO request_receipts (owner_id, operation, request_key, payload_hash, result_id, created_at)
                VALUES (?, 'approve_proposal', ?, ?, ?, ?)""",
                (LOCAL_OWNER, request_key, payload_hash, task_id, now),
            )
            task = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._task_dict(connection, task)

    def _validate_edits(self, proposal: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
        title = str(edits.get("title", proposal["title"])).strip()[:140]
        if not title:
            raise ServiceError("A task needs a title.")
        description = str(edits.get("description", proposal["description"])).strip()[:500]
        due_date = self._normalise_date(edits.get("due_date", proposal["due_date"]))
        work_start_at = self._normalise_datetime(edits.get("work_start_at", proposal["work_start_at"]))
        raw_steps = edits.get("steps", proposal["suggested_steps"])
        if not isinstance(raw_steps, list):
            raise ServiceError("Steps must be a list of lines.")
        steps: list[str] = []
        seen: set[str] = set()
        for value in raw_steps:
            step = str(value).strip()[:180]
            if step and step.casefold() not in seen:
                seen.add(step.casefold())
                steps.append(step)
        if len(steps) > 12:
            raise ServiceError("Keep the first version to 12 steps or fewer.")
        if proposal["kind"] == "idea":
            steps = []
        return {"title": title, "description": description, "due_date": due_date, "work_start_at": work_start_at, "steps": steps}

    def dismiss_proposal(self, proposal_id: str) -> None:
        with self.database.connect() as connection:
            result = connection.execute(
                "UPDATE proposals SET state = 'dismissed', updated_at = ? WHERE id = ? AND state = 'draft'",
                (self._now(), proposal_id),
            )
            if result.rowcount == 0:
                raise ConflictError("That proposal is no longer an active draft.")

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE owner_id = ? ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, created_at DESC",
                (LOCAL_OWNER,),
            ).fetchall()
            return [self._task_dict(connection, row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ? AND owner_id = ?", (task_id, LOCAL_OWNER)).fetchone()
            if row is None:
                raise NotFoundError("Task not found.")
            return self._task_dict(connection, row)

    def _task_dict(self, connection: Any, row: Any) -> dict[str, Any]:
        task = dict(row)
        steps = connection.execute("SELECT * FROM steps WHERE task_id = ? ORDER BY position", (task["id"],)).fetchall()
        task["steps"] = [dict(step) | {"completed": bool(step["completed"])} for step in steps]
        return task

    def set_task_status(self, task_id: str, status: str) -> dict[str, Any]:
        if status not in {"open", "completed", "cancelled"}:
            raise ServiceError("Unsupported task status.")
        with self.database.connect() as connection:
            result = connection.execute(
                "UPDATE tasks SET status = ?, revision = revision + 1, updated_at = ? WHERE id = ? AND owner_id = ?",
                (status, self._now(), task_id, LOCAL_OWNER),
            )
            if result.rowcount == 0:
                raise NotFoundError("Task not found.")
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._task_dict(connection, row)

    def set_step_completed(self, step_id: str, completed: bool) -> dict[str, Any]:
        with self.database.connect() as connection:
            step = connection.execute(
                """SELECT s.*, t.owner_id FROM steps s JOIN tasks t ON t.id = s.task_id
                WHERE s.id = ? AND t.owner_id = ?""",
                (step_id, LOCAL_OWNER),
            ).fetchone()
            if step is None:
                raise NotFoundError("Step not found.")
            connection.execute(
                "UPDATE steps SET completed = ?, revision = revision + 1, updated_at = ? WHERE id = ?",
                (int(completed), self._now(), step_id),
            )
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (step["task_id"],)).fetchone()
            return self._task_dict(connection, row)

    def answer_about_tasks(self, message: str) -> str:
        message = message.strip()
        if not message:
            raise ServiceError("Ask a question about your saved work.")
        return self.planner.answer_about_tasks(message, self.list_tasks()[:30])

    def delete_capture(self, capture_id: str) -> None:
        capture = self.get_capture(capture_id)
        audio_path = Path(capture["audio_path"]) if capture["audio_path"] else None
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError as error:
                raise ServiceError("The audio file could not be removed. Nothing was deleted; retry this action.") from error
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE tasks SET source_capture_id = NULL, source_excerpt = NULL, proposal_id = NULL, updated_at = ? WHERE source_capture_id = ?",
                (self._now(), capture_id),
            )
            connection.execute("DELETE FROM captures WHERE id = ? AND owner_id = ?", (capture_id, LOCAL_OWNER))

    def _clarification_replies(self, capture_id: str, revision: int) -> list[dict[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT question, answer, skipped FROM clarifications WHERE capture_id = ? AND revision = ?
                AND (answer IS NOT NULL OR skipped = 1) ORDER BY created_at""",
                (capture_id, revision),
            ).fetchall()
        return [{"question": row["question"], "answer": row["answer"] or "[skipped]"} for row in rows]

    def _clarification_count(self, capture_id: str, revision: int) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM clarifications WHERE capture_id = ? AND revision = ?",
                (capture_id, revision),
            ).fetchone()
        return int(row["count"])

    def _normalise_date(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError as error:
            raise ServiceError("Deadline must use YYYY-MM-DD, or be left blank.") from error

    def _normalise_datetime(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ServiceError("Suggested work time must be ISO-8601 with a timezone, or be left blank.") from error
        if parsed.tzinfo is None:
            raise ServiceError("Suggested work time needs a timezone offset, or can be left blank.")
        return parsed.isoformat()

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _now(self) -> str:
        return datetime.now(self._timezone).isoformat()
