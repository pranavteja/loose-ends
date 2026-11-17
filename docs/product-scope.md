# Product scope and acceptance criteria

## Phase A: personal companion and internal board

Voice conversation → optional clarification → suggested steps → review → internal task board. The home-screen companion answers spoken questions about saved work. Support short English voice sessions with one speaker and one level of subtasks. Talk intentionally has no typed or transcript-based chat.

Deadlines and suggested work times are different fields. Neither is mandatory. No actual reminder delivery is included in Phase A. Suggestions must not be presented as scheduled notifications.

| ID | Requirement | Acceptance evidence |
|---|---|---|
| AC01 | Preserve capture | Text/audio saved before inference; ID survives reload |
| AC02 | Recover failures | Retry reuses input; no duplicate active proposal set |
| AC03 | Ground intent | Task/idea has a source excerpt; suggested steps labelled separately |
| AC04 | Respect intent | Negation excluded; tentative ideas separate; cancellation distinguished |
| AC05 | Preserve corrections | Final corrected timing wins, or ambiguity is visible |
| AC06 | Handle dates | Relative dates use capture time/timezone; no invented deadlines |
| AC07 | Clarify optionally | Answer, skip, and fewer-questions controls all lead to a reviewable draft |
| AC08 | Decompose | Short editable steps without unsupported claims or mandatory invented dates |
| AC09 | Review independently | Approve/edit/dismiss one proposal without changing others |
| AC10 | Avoid duplicate saves | Retried approval creates exactly one task and its steps |
| AC11 | Persist progress | Task and step changes survive refresh/restart |
| AC12 | Keep revisions separate | Spoken correction supersedes the pending draft, not approved tasks |
| AC13 | Make voice requirements clear | Microphone/speech unavailable → actionable error; Review and Board remain usable |
| AC14 | Ground companion answers | Answers refer to saved tasks and do not invent completion |
| AC15 | Separate suggestions from writes | Voice guidance does not silently alter approved task state |
| AC16 | Keep Kane optional at runtime | App starts and core flow works without Kane credentials |
| AC17 | Delete capture consistently | Audio/source context removed according to documented policy |

Proposed deletion policy: deleting a capture removes its audio, transcript, clarification messages and pending drafts. Approved tasks remain unless explicitly selected for deletion; their source pointers and copied source excerpts are removed. Explain this before deletion. A file-removal failure must be visible and retryable, not reported as complete.

## Phase B

Bot-proposed edits, priorities and rescheduling use the same application's backend. Show a before/after preview and apply only approved changes. Add reliable reminders once scheduling and notification delivery exist. Calendar integrations use service APIs and OAuth. No computer-use agents are planned.

## Later

Calendar availability, platform-dependent app-usage signals, explicit working-style preferences, optional gamification, reflection, richer inputs and model personalisation. Avoid deriving fixed personality labels from a few conversations.

## Evaluation

Measure intent extraction, unnecessary questions, step usefulness, invented dates, task-answer grounding, edits before approval, latency and duplicate saves. Keep transcription errors separate from planning failures. Use the synthetic evaluation fixtures as a starting point; they are not a benchmark result.
