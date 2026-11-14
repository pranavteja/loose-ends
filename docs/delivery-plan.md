# Delivery plan

The approved scope adds clarification, decomposition and a task-aware bot beyond the original inbox. Treat the earlier 25–35 hour estimate as superseded. A provisional budget is 35–50 combined engineering hours for a modest prototype, including integration and demo work; validate this after the first slice. This is not a delivery guarantee.

## Build in useful slices

| Slice | Deliverable | Done when |
|---|---|---|
| 1 | Typed capture → draft → approval → board | Data persists; first Kane flow verifies it |
| 2 | Optional clarification and editable steps | Skip works; steps save with parent task |
| 3 | Browser voice recording | Transcript editable; failed inference can retry |
| 4 | Task-aware home bot | Answers use saved tasks; no hidden writes |
| 5 | Reliability and demo | Revision/duplicate checks pass; mobile layout reviewed |

Keep Gradio Blocks and one Python application. Do not start with a queue, React build, Java/Python service split, or separate agents for every role.

## Proposed event schedule (IST)

| Date | Focus |
|---|---|
| Nov 14 | Final detailed review, credential/tool spike, agree contracts |
| Nov 15 | Slice 1 and first agent/Kane evidence |
| Nov 16 | Clarification and essential substeps |
| Nov 17 | Recording and grounded task chat |
| Nov 18 | Failure cases, mobile checks, access/setup |
| Nov 19 | Freeze, three-minute demo and submission by 23:59 |

If capacity is insufficient, reduce question rounds, filters and visual polish. Keep one clarification or skip path, essential steps, bot access, and the full save loop. Defer audio uploads, autonomous updates, reminders and integrations entirely.

## Suggested team split

| Owner | Work | Handoff |
|---|---|---|
| Pranav | Model adapters, prompts, evaluation, transcription | Validated proposal examples and error cases |
| Backend colleague | Service contracts, SQLite, transactions, revisions, deployment | Typed service inputs/results |
| Shared | Gradio Blocks interfaces and Kane integration | One owner for each acceptance criterion |

Responsibilities require the colleague's agreement; nobody has been invited or assigned automatically. Python is the agreed starting direction; confirm comfort before coding rather than adding a second backend by default.

## Definition of done

Real input reaches actual inference, approved tasks/steps persist, and the bot answers from saved state. Retries do not duplicate saves. Meaningful Kane evidence reaches the coding agent; ordinary tests work independently. No passing run is claimed before execution. Setup instructions match actual commands, and any fixture replay is clearly labelled. The shared demo uses synthetic data and works without reviewer model downloads.

## After the hackathon

Use it personally first. Record where clarification helps versus annoys. Add approved plan updates, then reminders or calendar integration based on that evidence. Personalisation starts with editable preferences, not fine-tuning. Revisit infrastructure only when measured needs justify it.

## First-day framework checks

Prove microphone capture on Debian and the target phone, one editable proposal with steps, a refresh that restores saved data, and a meaningful Kane run on the rendered UI. Check duplicate approvals and stale inference results. These are implementation gates, not claims that tests have already passed. Pin the tested package version after the spike. Do not build both Gradio and another frontend in parallel.
