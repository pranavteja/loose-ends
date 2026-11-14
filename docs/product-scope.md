# Product scope

Proposal v0.1 — review before implementation.

## User and outcome

Initial user: an individual capturing personal commitments from desktop or mobile browser. Success means fewer lost commitments and less manual editing, not maximum autonomous execution.

## Core journey

1. Record a voice note (up to two minutes), upload audio, or paste text.
2. See queued/processing/failed states and retain input through failures.
3. Read and edit the transcript; re-extract proposals if necessary.
4. Review each task or idea with its supporting source excerpt.
5. Confirm proposed dates, resolve ambiguities, and approve selected items.
6. View saved tasks and ideas, edit them, and mark tasks complete.

Use explicit start/stop recording; natural pauses must not submit a recording prematurely. English, one speaker, and short captures are the initial supported scope.

## Acceptance criteria

| ID | Requirement | Observable result |
|---|---|---|
| AC01 | Capture text or audio | Input is persisted and receives a stable capture ID |
| AC02 | Recover from processing failure | Retry uses the same capture; no lost text/audio or duplicate proposals |
| AC03 | Preserve evidence | Every proposed action has a source excerpt from the current transcript |
| AC04 | Distinguish intent | Negated tasks are excluded; tentative ideas are separated from tasks |
| AC05 | Handle corrections | “Friday, actually Monday” yields Monday or requests clarification |
| AC06 | Resolve time honestly | Capture timestamp/timezone are used; ambiguity is flagged; missing dates remain empty |
| AC07 | Review controls | Edit/approve/dismiss operate independently on each proposal |
| AC08 | Approve idempotently | Double click or retried approval produces exactly one inbox item |
| AC09 | Persist inbox | Approved items and completion state survive reload/restart |
| AC10 | Version transcript edits | Regeneration invalidates unapproved old proposals; approved tasks are not silently rewritten |
| AC11 | Handle unavailable microphone | Pasted text and audio upload remain available |
| AC12 | Delete capture | Associated audio is removed; retained approved tasks no longer expose deleted source text |

For deletion, show the user whether related tasks will be retained or deleted; default to retaining approved tasks while removing their source link. A failed file deletion remains a retryable cleanup job.

## Conditional browser execution

A separate approval enables one allowed action, such as creating a task in a selected board. Store a snapshot of the approved payload. Execution cannot use a later edited proposal without renewed approval.

| ID | Requirement | Observable result |
|---|---|---|
| BX01 | Explicit execution approval | No external write occurs on transcription or inbox approval alone |
| BX02 | Verify completion | Destination item and fields match the approved payload |
| BX03 | Handle uncertain completion | Timeout after a possible write produces `unknown`, not automatic retry |
| BX04 | Reconcile duplicates | Check for the previously created item before allowing another attempt |
| BX05 | Session expiry | Show authentication-needed status; preserve approved work |

Defer runtime browser execution if the chosen destination fails the initial feasibility spike. Keep Kane development verification regardless.

## Excluded from week one

Continuous listening, live calls, email sending, payments/bookings, arbitrary websites, multi-user collaboration, recurring jobs, background reminders, calendar sync, vector search, fine-tuning, and broad multilingual support.

## Success measures

Measure supported-case extraction quality, invented-date rate, edits per approved task, end-to-end latency, processing failures, and duplicate approvals. Report audio transcription errors separately from extraction errors. Targets should be set after measuring the initial fixtures; no accuracy claim is made yet.
