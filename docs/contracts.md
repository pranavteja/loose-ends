# Proposed API and data contracts

These interfaces are design drafts, not implemented endpoints.

## HTTP surface

| Method and route | Behaviour |
|---|---|
| POST /captures | Accept text or multipart audio, captured_at, timezone; return 202 with capture/job IDs |
| GET /captures/{id} | Return processing state, transcript revision, and current proposals |
| PATCH /captures/{id}/transcript | Optimistic revision check; save edit and enqueue extraction |
| POST /captures/{id}/retry | Retry failed stage with stable job identity |
| POST /proposals/{id}/approve | Validate revision and edits; atomically create one inbox item |
| POST /proposals/{id}/dismiss | Dismiss a pending proposal |
| GET /items | Filter by type, date, completion state |
| PATCH /items/{id} | Edit or complete with revision guard |
| DELETE /captures/{id} | Apply selected task-retention policy; enqueue audio cleanup |
| POST /items/{id}/executions | Conditional: explicitly approve a destination/payload snapshot |
| GET /executions/{id} | Conditional: status and evidence references |

Mutations use an idempotency key where retries can create records. Conflicting revisions return 409, invalid data 422, inaccessible records 404, and provider failures surface as job errors. Enforce file-size/duration limits server-side and validate media; the browser's MIME label is not sufficient.

## Records

| Entity | Key fields |
|---|---|
| Capture | id, owner_id, type, captured_at, timezone, audio_path, transcript, revision, status |
| Proposal | id, capture_id, revision, type, title, description, source_excerpt, timing_phrase, due_date, due_at, timezone, needs_clarification, state |
| InboxItem | id, owner_id, proposal_id, type, title, description, due_date/due_at, timezone, status, revision |
| Job | id, capture_id, stage, revision, status, attempts, lease_until, error_code |
| Execution | id, item_id, destination, approved_payload, idempotency_key, status, destination_item_id, evidence_ref |

Unique proposal_id on InboxItem prevents duplicate approval. Do not persist raw authentication cookies in these records. Resolve source excerpts against the transcript; flag unsupported excerpts. No self-reported model confidence score is treated as calibrated probability.

## Provider interfaces

`transcribe(audio_reference) -> transcript + optional segments`

`extract_actions(transcript, captured_at, timezone) -> validated proposal candidates`

The backend, not the model, assigns IDs and status. Empty action lists are valid. Retry transient provider failures with a bounded policy; malformed output gets at most a bounded repair attempt before a visible failure. Never silently discard a capture.
