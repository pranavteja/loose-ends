# Backend contracts — proposed, not implemented

The browser and Python backend agree on these messages. A contract describes inputs, outputs and failure behaviour so UI and backend work can progress independently.

## Python service contracts first

Gradio event handlers call these functions. Keep Gradio component objects out of the service layer so it can be tested independently and exposed through HTTP later.

| Service operation | Behaviour |
|---|---|
| create_capture(owner, input, captured_at, timezone, request_key) | Persist text/audio and return capture ID/revision |
| process_capture(owner, capture_id, revision) | Bounded inference; persist attempt and draft or failure |
| get_capture(owner, capture_id) | Return current transcript, question, draft and status |
| edit_transcript(owner, capture_id, revision, text) | Save new revision and supersede pending draft |
| answer_clarification(owner, capture_id, revision, answer_or_skip) | Persist answer and refine draft |
| approve_proposal(owner, proposal_id, revision, edits, request_key) | Save task and steps in one transaction |
| dismiss_proposal(owner, proposal_id, revision) | Dismiss current proposal |
| list_tasks(owner, filters) | Read durable board contents |
| update_task / update_step(owner, id, revision, changes) | Explicit edits or completion |
| answer_about_tasks(owner, message) | Grounded answer without task mutation |
| delete_capture(owner, capture_id, retention_choice) | Remove source under documented retention policy |

UI handlers translate structured success/errors into visible controls. Error categories: conflict, invalid_input, not_found, provider_unavailable and processing_failed. If a REST API is introduced later, map these to HTTP statuses then; the MVP does not need a parallel collection of handwritten routes.

Capture creation and approval use request keys. Identical retries return the saved result; a reused key with a different payload conflicts. Processing uses attempt IDs and revisions to reject stale results. After an uncertain response, read persisted status before retrying. Gradio's queue schedules events but does not guarantee recovery after a server crash. Persist input first, mark abandoned attempts retryable on restart, and enforce audio limits in backend code.

## Minimal records

| Record | Main fields |
|---|---|
| Capture | id, owner_id, type, captured_at, timezone, audio_path, transcript, revision, state, attempt_id, attempt_started_at, error_code |
| Clarification | id, capture_id, revision, question, answer, skipped, created_at |
| Proposal | id, capture_id, revision, type, title, description, source_excerpt, timing_phrase, due_date, due_at, work_start_at, timezone, needs_clarification, state, proposed_steps |
| Task | id, owner_id, proposal_id, type, title, description, due_date, due_at, work_start_at, timezone, status, revision |
| Step | id, task_id, position, title, completed, revision |
| RequestReceipt | owner_id, operation, request_key, payload_hash, result_id |

Store proposed steps as validated JSON initially; approved steps become separate rows. Enforce one Task per proposal_id. Choose either due_date or due_at, not contradictory values. Ideas can be stored in Task with type=idea, excluded from active-task lists. Source metadata is separate from user-edited task text.

A transaction writes the task, steps, and approval state together. This avoids a task saved without its steps if the process fails. Revision comparisons avoid overwriting a newer edit. Use owner_id checks even in a single-user deployment so later authentication does not depend on retrofitting every query.

## Model boundaries

- `transcribe(audio) -> transcript`
- `propose_plan(transcript, replies, captured_at, timezone, question_budget) -> question_or_proposals`
- `answer_about_tasks(message, task_context) -> answer + referenced_task_ids`

One provider can implement all roles. IDs, database writes and permissions belong to backend code. Models suggest content, not SQL, shell commands or arbitrary tool calls. Null dates and empty action lists are valid.

## Later contracts

Phase B adds proposed-change records with original task revision and approved before/after values. Calendar integration adds an OAuth connection and sync records. Reminder scheduling adds notification delivery state. These records are deliberately absent from the Phase A schema.
