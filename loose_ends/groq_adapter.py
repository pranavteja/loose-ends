"""Provider boundary for Groq transcription and planning calls."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings


class ProviderError(RuntimeError):
    """A safe-to-display description of an unavailable or invalid model call."""


# GPT-OSS 20B supports strict structured output. Every property is required;
# nullable values represent information that the user did not provide.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "question": {"type": ["string", "null"]},
        "question_reason": {"type": ["string", "null"]},
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["task", "idea"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "source_excerpt": {"type": "string"},
                    "timing_phrase": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "work_start_at": {"type": ["string", "null"]},
                    "needs_clarification": {"type": "boolean"},
                    "missing_detail": {"type": ["string", "null"]},
                    "suggested_steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "kind", "title", "description", "source_excerpt", "timing_phrase", "due_date",
                    "work_start_at", "needs_clarification", "missing_detail", "suggested_steps",
                ],
            },
        },
    },
    "required": ["summary", "question", "question_reason", "proposals"],
}


PLANNER_INSTRUCTIONS = """You turn a person's short note into reviewable planning drafts.
Return only the requested JSON schema. You propose content; you never claim to
create reminders, send messages, change external systems, or mark work complete.

Rules:
- Preserve intent. A tentative thought explicitly saying not to make a task is an idea.
- Do not create a task for something explicitly cancelled, completed, or negated.
- Source excerpts must quote or closely reproduce only the supplied note.
- Keep steps short, editable, and useful. Do not assume a draft, attachment, recipient,
  budget, or progress the person did not state.
- A deadline (due_date) differs from a suggested work session (work_start_at).
- If a note corrects an earlier time, use the final explicit correction. If timing remains
  ambiguous, leave the date null and explain what is missing rather than guessing.
- Return due_date only as YYYY-MM-DD when it is confidently resolvable. Return
  work_start_at only as an ISO-8601 datetime with offset when it is confidently resolvable.
  Missing or ambiguous timing stays null and is explained in missing_detail.
- Ask at most one focused optional question only when it would materially improve a plan.
  If the question budget is zero, question and question_reason must be null.
- It is valid to return no proposals for conversation, completed work, or no-action notes.
"""


class GroqAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self):
        if not self.settings.groq_api_key:
            raise ProviderError("Add GROQ_API_KEY to .env, then retry this saved capture.")
        try:
            from groq import Groq
        except ImportError as error:  # pragma: no cover - setup issue
            raise ProviderError("Dependencies are not installed. Run pip install -r requirements.txt.") from error
        return Groq(api_key=self.settings.groq_api_key, timeout=45.0, max_retries=1)

    def transcribe(self, audio_path: Path) -> str:
        try:
            with audio_path.open("rb") as audio_file:
                response = self._client().audio.transcriptions.create(
                    file=audio_file,
                    model=self.settings.transcription_model,
                    language="en",
                    temperature=0.0,
                    response_format="json",
                )
            text = getattr(response, "text", "")
            if not isinstance(text, str) or not text.strip():
                raise ProviderError("Groq returned an empty transcript. Please retry or type the note instead.")
            return text.strip()
        except ProviderError:
            raise
        except Exception as error:  # The SDK error may contain credentials or request data.
            raise ProviderError("Transcription could not be completed. Your recording is saved; please retry.") from error

    def propose_plan(
        self,
        transcript: str,
        replies: list[dict[str, str]],
        captured_at: str,
        timezone: str,
        question_budget: int,
    ) -> dict[str, Any]:
        context = {
            "captured_at": captured_at,
            "timezone": timezone,
            "question_budget": question_budget,
            "note": transcript,
            "clarification_replies": replies,
        }
        try:
            response = self._client().chat.completions.create(
                model=self.settings.extraction_model,
                temperature=0.2,
                max_completion_tokens=1200,
                messages=[
                    {"role": "system", "content": PLANNER_INSTRUCTIONS},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "planning_draft", "strict": True, "schema": PLAN_SCHEMA},
                },
            )
            content = response.choices[0].message.content
            return validate_plan(json.loads(content or "{}"), transcript, question_budget)
        except ProviderError:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("The planning response was invalid. The capture is saved; please retry.") from error
        except Exception as error:
            raise ProviderError("Planning is temporarily unavailable. The capture is saved; please retry.") from error

    def answer_about_tasks(self, message: str, task_context: list[dict[str, Any]]) -> str:
        if not task_context:
            return "You do not have any saved tasks or ideas yet. Capture a thought when you are ready."
        prompt = {
            "question": message,
            "saved_task_context": task_context,
            "instructions": (
                "Answer only from saved_task_context. Mention task titles when useful. "
                "Do not invent dates, completion, steps, or priorities. Do not change data or imply any change was made. "
                "If the answer is not in the saved context, say so plainly. Keep the answer concise."
            ),
        }
        try:
            response = self._client().chat.completions.create(
                model=self.settings.extraction_model,
                temperature=0.2,
                max_completion_tokens=500,
                messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            )
            answer = response.choices[0].message.content
            if not isinstance(answer, str) or not answer.strip():
                raise ProviderError("The companion returned an empty answer. Please try again.")
            return answer.strip()
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError("The companion is temporarily unavailable. No task data was changed.") from error


def validate_plan(raw: Any, transcript: str, question_budget: int) -> dict[str, Any]:
    """Apply application-level guardrails that JSON syntax alone cannot provide."""
    if not isinstance(raw, dict):
        raise ValueError("Plan is not an object")
    raw_proposals = raw.get("proposals", [])
    if not isinstance(raw_proposals, list):
        raise ValueError("proposals is not a list")

    proposals: list[dict[str, Any]] = []
    for candidate in raw_proposals[:5]:
        if not isinstance(candidate, dict):
            continue
        title = _text(candidate.get("title"), 140)
        if not title:
            continue
        kind = candidate.get("kind") if candidate.get("kind") in {"task", "idea"} else "task"
        proposals.append(
            {
                "kind": kind,
                "title": title,
                "description": _text(candidate.get("description"), 500),
                "source_excerpt": _ground_excerpt(transcript, _text(candidate.get("source_excerpt"), 280)),
                "timing_phrase": _nullable_text(candidate.get("timing_phrase"), 160),
                "due_date": _date_or_none(candidate.get("due_date")),
                "work_start_at": _datetime_or_none(candidate.get("work_start_at")),
                "needs_clarification": bool(candidate.get("needs_clarification")),
                "missing_detail": _nullable_text(candidate.get("missing_detail"), 240),
                "suggested_steps": _steps(candidate.get("suggested_steps")) if kind == "task" else [],
            }
        )

    question = _nullable_text(raw.get("question"), 360) if question_budget > 0 else None
    return {
        "summary": _text(raw.get("summary"), 500) or "Draft ready for review.",
        "question": question,
        "question_reason": _nullable_text(raw.get("question_reason"), 240) if question else None,
        "proposals": proposals,
    }


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _nullable_text(value: Any, limit: int) -> str | None:
    text = _text(value, limit)
    return text or None


def _date_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _datetime_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo else None


def _steps(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        step = _text(item, 180)
        key = step.casefold()
        if step and key not in seen:
            seen.add(key)
            result.append(step)
        if len(result) == 7:
            break
    return result


def _ground_excerpt(transcript: str, candidate: str) -> str:
    if candidate and candidate.casefold() in transcript.casefold():
        return candidate
    return transcript.strip()[:280]
