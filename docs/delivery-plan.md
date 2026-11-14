# Delivery plan and collaboration

Estimated core MVP: 25–35 focused engineering hours, plus deployment/tool uncertainty. This is a planning estimate, not a commitment. The optional external-action runner needs a separate time budget and is the first scope cut.

## First decisions and feasibility checks

1. Agree core inbox versus one external browser action.
2. Confirm Kane credentials; run a meaningful browser flow on a minimal local page and confirm how results reach the coding agent.
3. Test Groq transcription/extraction on representative synthetic notes, or benchmark local models.
4. If external execution is selected, prove one allowed destination operation and its verification before building around it.

## Remaining event window

| Date (IST) | Outcome |
|---|---|
| Nov 14 | Review scope, initialise repository, tool/model feasibility |
| Nov 15 | Text → proposals → review → saved inbox, with first Kane verification |
| Nov 16 | Audio capture and transcription; worker failures/retries |
| Nov 17 | Corrections, dates, idempotency; conditional destination spike if capacity allows |
| Nov 18 | Evaluation, mobile UX, deployment, agent/Kane evidence |
| Nov 19 | Stabilise, record three-minute demo, prepare posts and submission before 23:59 IST |

If time shrinks, cut external execution, audio upload, and extra filters first. Keep the main record → review → save path, evidence links, idempotency, and Kane integration.

## Suggested ownership, pending agreement

| Workstream | Proposed lead | Handoff |
|---|---|---|
| Extraction, transcription adapters, fixtures/evaluation | Pranav | Typed outputs and documented failure cases |
| API, persistence, jobs, idempotency, authentication/deployment | Backend colleague | Endpoint contracts and local startup |
| Frontend review flow | Shared / coding-agent assisted | Agree API shapes before parallel implementation |
| Kane verification and demo | Shared | One named owner for each acceptance criterion |

No collaborator has been invited or assigned work. Choose owners together.

## Definition of MVP done

- Real audio or text passes through actual configured inference into review and persisted tasks.
- Error states are visible; retry/approval cannot create duplicates.
- A small model evaluation report distinguishes extraction from transcription failures.
- Kane has run meaningful acceptance flows and its result has reached the coding agent.
- README has actual setup/start commands and accurate prerequisites.
- Reviewers can access a working demo without first downloading model weights.
- Evidence and demo match the shipped commit; replay fixtures are clearly labelled.

## Beyond the event

First use the app for a week and record friction. Then choose reminders or one destination integration, followed by screenshots/documents, semantic deduplication, and local/cloud benchmarks. Fine-tuning follows an evaluation set and recurring failure evidence, not the initial scaffold.
