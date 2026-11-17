"""Regression tests for durable capture, review, approval, and progress behaviour."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from loose_ends.config import Settings
from loose_ends.database import Database
from loose_ends.services import LooseEndsService
from loose_ends.voice_agent import _is_explicit_draft_request, _is_explicit_draft_revision


class FakePlanner:
    def __init__(self, question: str | None = None) -> None:
        self.question = question
        self.calls: list[list[dict[str, str]]] = []

    def transcribe(self, audio_path: Path) -> str:
        return "Transcribed note"

    def propose_plan(self, transcript: str, replies: list[dict[str, str]], captured_at: str, timezone: str, question_budget: int) -> dict[str, Any]:
        self.calls.append(replies)
        return {
            "summary": "Draft ready.",
            "question": self.question if question_budget else None,
            "question_reason": None,
            "proposals": [{
                "kind": "task", "title": "Send proposal", "description": "", "source_excerpt": transcript,
                "timing_phrase": "tomorrow", "due_date": None, "work_start_at": None,
                "needs_clarification": False, "missing_detail": "No deadline assumed.",
                "suggested_steps": ["Review the draft", "Send it"],
            }],
        }

    def answer_about_tasks(self, message: str, task_context: list[dict[str, Any]]) -> str:
        return f"Saved tasks: {', '.join(task['title'] for task in task_context)}"


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.settings = Settings(
            data_dir=root, audio_dir=root / "audio", database_path=root / "test.sqlite3", groq_api_key=None,
            transcription_model="whisper-large-v3-turbo", extraction_model="openai/gpt-oss-20b",
            timezone="Asia/Kolkata", host="127.0.0.1", port=7860, max_audio_bytes=25 * 1024 * 1024,
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path)
        self.database.initialize()
        self.planner = FakePlanner()
        self.service = LooseEndsService(self.database, self.planner, self.settings)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_approval_is_idempotent_and_steps_persist(self) -> None:
        capture_id = self.service.create_text_capture("Send proposal tomorrow")
        self.service.process_capture(capture_id)
        proposal = self.service.list_review_proposals()[0]
        first = self.service.approve_proposal(proposal["id"], {"steps": ["Review the draft", "Send it"]})
        second = self.service.approve_proposal(proposal["id"], {"steps": ["Review the draft", "Send it"]})
        self.assertEqual(first["id"], second["id"])
        tasks = self.service.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual([step["title"] for step in tasks[0]["steps"]], ["Review the draft", "Send it"])

    def test_skip_clarification_keeps_a_reviewable_draft(self) -> None:
        self.planner.question = "Is the proposal drafted?"
        capture_id = self.service.create_text_capture("Send a proposal")
        first = self.service.process_capture(capture_id)
        self.assertEqual(first.question, "Is the proposal drafted?")
        result = self.service.answer_clarification(capture_id, "", skip=True)
        self.assertIsNone(result.question)
        self.assertEqual(len(self.service.list_review_proposals()), 1)
        self.assertEqual(self.planner.calls[-1], [{"question": "Is the proposal drafted?", "answer": "[skipped]"}])

    def test_progress_survives_reopen(self) -> None:
        capture_id = self.service.create_text_capture("Send a proposal")
        self.service.process_capture(capture_id)
        proposal = self.service.list_review_proposals()[0]
        task = self.service.approve_proposal(proposal["id"], {})
        self.service.set_step_completed(task["steps"][0]["id"], True)
        reloaded = LooseEndsService(self.database, self.planner, self.settings).get_task(task["id"])
        self.assertTrue(reloaded["steps"][0]["completed"])
        self.assertFalse(reloaded["steps"][1]["completed"])

    def test_clarification_rounds_are_bounded(self) -> None:
        self.planner.question = "One focused question?"
        capture_id = self.service.create_text_capture("Plan the proposal")
        self.service.process_capture(capture_id)
        second = self.service.answer_clarification(capture_id, "Yes")
        self.assertEqual(second.question, "One focused question?")
        final = self.service.answer_clarification(capture_id, "Still yes")
        self.assertIsNone(final.question)

    def test_draft_creation_requires_an_explicit_affirmative_request(self) -> None:
        self.assertTrue(_is_explicit_draft_request("Okay, make a draft now"))
        self.assertTrue(_is_explicit_draft_request("Send this to review"))
        self.assertFalse(_is_explicit_draft_request("I need to send a parcel"))
        self.assertFalse(_is_explicit_draft_request("Don't make a draft yet"))

    def test_draft_revision_requires_an_explicit_correction(self) -> None:
        self.assertTrue(_is_explicit_draft_revision("Actually, change the date to Friday"))
        self.assertTrue(_is_explicit_draft_revision("Remove the second step"))
        self.assertFalse(_is_explicit_draft_revision("That sounds good"))
        self.assertFalse(_is_explicit_draft_revision("Don't change the date"))

    def test_voice_revision_supersedes_the_previous_review_draft(self) -> None:
        capture_id = self.service.create_text_capture("Send the proposal tomorrow")
        self.service.process_capture(capture_id, question_budget=0)
        first = self.service.list_review_proposals()[0]

        self.service.edit_transcript_and_process(capture_id, "Send the revised proposal on Friday")

        review = self.service.list_review_proposals()
        self.assertEqual(len(review), 1)
        self.assertNotEqual(review[0]["id"], first["id"])
        self.assertEqual(review[0]["source_excerpt"], "Send the revised proposal on Friday")
        self.assertEqual(self.service.get_proposal(first["id"])["state"], "superseded")


if __name__ == "__main__":
    unittest.main()
