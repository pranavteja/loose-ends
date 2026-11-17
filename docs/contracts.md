# Backend contracts

The unified browser shell calls a small loopback-only JSON API. Python services remain the business boundary: HTTP handlers translate requests and errors but do not duplicate validation or persistence rules.

## Implemented browser API

| Method and path | Purpose | Main result |
|---|---|---|
| `GET /api/health` | Check Groq/LiveKit configuration | readiness, missing values, agent name |
| `POST /api/token` | Create an opaque LiveKit room identity and dispatch the agent | server URL and short-lived participant token |
| `GET /api/review` | Load active draft proposals | proposal list with suggested steps and source context |
| `POST /api/review/{id}/approve` | Validate edits and atomically create a board record | saved task with steps |
| `POST /api/review/{id}/dismiss` | Dismiss an active proposal | confirmation |
| `GET /api/board` | Load approved tasks, ideas, and step state | task list |
| `PATCH /api/tasks/{id}/status` | Set `open`, `completed`, or `cancelled` | updated task |
| `PATCH /api/steps/{id}` | Set step completion explicitly | updated parent task |

The server maps invalid input to 400, missing records to 404, and stale/conflicting state to 409. Provider and LiveKit credentials never appear in these responses.

## Python service boundary

| Service operation | Behaviour |
|---|---|
| `create_text_capture` / `create_audio_capture` | Persist original input before planning. |
| `process_capture` | Run bounded inference and persist a draft or retryable failure. |
| `answer_clarification` | Save an answer or skip and refine within the question budget. |
| `list_review_proposals` | Return active review drafts only. |
| `approve_proposal` | Validate edits and save task, steps, receipt, and proposal state transactionally. |
| `dismiss_proposal` | Remove a draft from active review without creating a task. |
| `list_tasks` | Return durable board contents with ordered steps. |
| `set_task_status` / `set_step_completed` | Apply explicit progress changes. |
| `answer_about_tasks` | Ground an answer in saved work without mutation. |

Approval is idempotent by proposal: repeated approval returns the existing task. A reused request key with a different payload conflicts. Processing uses attempt IDs and revisions so stale model results cannot overwrite a newer capture.

## Minimal records

| Record | Main fields |
|---|---|
| Capture | id, owner_id, input_type, transcript/audio, captured_at, timezone, revision, state, attempt_id |
| Clarification | id, capture_id, revision, question, answer, skipped |
| Proposal | id, capture_id, revision, kind, title, description, source_excerpt, timing, proposed_steps, state |
| Task | id, owner_id, proposal_id, kind, title, description, dates, status, revision |
| Step | id, task_id, position, title, completed, revision |
| RequestReceipt | owner_id, operation, request_key, payload_hash, result_id |

Ideas share the Task table with `kind=idea` and have no steps. Unknown dates are valid null values. Source context is stored separately from user-edited task wording.

## Model boundaries

- Voice agent: spoken turn → private Groq Whisper transcript → OSS 20B response → streaming Cartesia audio through LiveKit Inference; no chat text is rendered.
- Draft-create tool: explicit user request → validated proposal persisted by application services.
- Draft-revise tool: explicit spoken correction + active pending capture → supersede its earlier proposal and persist the current version.
- Structured planner: capture + replies + time context → question or proposals.
- Task-aware answer: message + bounded saved-task context → grounded response.

Models suggest content. IDs, authorization, validation, database writes, and task status belong to deterministic backend code.

## Later contracts

Public deployment needs authentication and real owner isolation. Phase B may add proposed-change records for edits to existing tasks. Calendar connections need OAuth and sync records. Reminder delivery needs scheduling and notification state. None of those actions should be implied by the current API.
