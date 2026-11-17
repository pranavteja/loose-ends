# Delivery plan

The voice-first shell is now the baseline. Do not continue parallel Gradio UI work. Development should deepen the complete Talk → Review → Board journey while retaining the Python service and SQLite boundaries.

## Build in useful slices

| Slice | Deliverable | Done when |
|---|---|---|
| 1 — complete | Real-time Talk experience | Turn-taking, captions, typed fallback, browser speech, and interruption work. |
| 2 — complete | Unified navigation and handoff | One port; no iframe; draft badge; end conversation opens Review. |
| 3 — complete | Editable Review and navigable Board | Approve/dismiss and task/step status work through local APIs. |
| 4 | Reliability pass | Join timeout, provider failures, stale drafts, and reconnects have tested recovery. |
| 5 | Device and accessibility pass | Keyboard, reduced motion, narrow layout, microphone permission, and system voices are checked. |
| 6 | Demo and evaluation | Synthetic end-to-end script is repeatable and logs/tests provide evidence. |

## Priority order

1. Protect the full successful journey and persistence.
2. Make failures recoverable without losing the conversation or draft.
3. Test the actual target browsers and microphone.
4. Improve transcription/prompt quality using recorded synthetic cases.
5. Add features only after the journey is dependable.

Defer external calendars, reminders, autonomous updates, nested subtasks, drag-and-drop, and a public multi-user deployment.

## Suggested ownership

| Area | Work | Handoff |
|---|---|---|
| Voice/model | Whisper/OSS 20B prompts, draft-tool behaviour, evaluation cases | Reproducible conversations and expected proposals |
| Backend | API/service contracts, SQLite integrity, conflicts, retention | Tested JSON and persistence behaviour |
| Frontend | Talk/Review/Board state, accessibility, device behaviour | Complete browser journey with clear recovery states |
| Shared | Demo script, synthetic data, regression evidence | One owner per acceptance criterion |

Assignments still require the people involved to agree; this table describes responsibility boundaries rather than assigning anyone automatically.

## Definition of done

- A user can start with speech, refine the thought, explicitly create a draft, edit it, approve it, and track it without leaving the product shell.
- The next action is clear at every empty, loading, success, and failure state.
- Secrets remain server-side and the default app is loopback-only.
- Repeated approval cannot duplicate a task; persisted state survives restart.
- Tests and the runbook match the commands that actually work.
- The demo uses synthetic content and does not depend on hidden manual database edits.

## After the first reliable demo

Use the app personally and record where turn detection, transcription, or clarification breaks the flow. Prefer prompt and interaction fixes backed by those cases. Add proposed updates to existing tasks before considering automatic changes. Personalisation should begin with explicit preferences rather than fine-tuning.
