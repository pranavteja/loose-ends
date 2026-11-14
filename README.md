# Loose Ends

**A voice-to-action inbox: capture a thought, review what it means, and track what actually happened.**

Status: **architecture proposal for review, 14 November 2026. No application is implemented yet.** Working name and stack are provisional.

Built toward the Kane CLI online hackathon, with a longer-term goal of a useful personal productivity application. Learning and sustained usefulness take priority over feature count.

## The problem

Commitments arrive as spoken thoughts, pasted messages, and half-formed plans. Manually turning them into tasks adds friction. Blindly executing model-generated instructions creates different problems: wrong dates, lost corrections, duplicates, and actions that were never intended.

Loose Ends keeps the original evidence, proposes structured actions, and lets the user approve the result.

## Example

> “Send the proposal to Alex tomorrow. Compare hosting options this weekend. Maybe try a new note-taking app, but don’t make that a task.”

The application proposes a task to send the proposal, asks for a concrete date for the weekend comparison if needed, and saves the last thought as an idea. It shows the source sentence for each proposal. Approving the first item creates a task in the inbox; it does **not** send the proposal.

## Proposed capabilities

| Capability | Core MVP | Later / conditional |
|---|---|---|
| Input | Browser voice recording, pasted text, short audio upload | Screenshots, documents, forwarded messages |
| Understanding | Editable transcript; tasks versus ideas; corrections; date proposals | Personal preferences, recurring commitments |
| Review | Edit, approve, dismiss; source excerpts; ambiguous-date flags | Conversational clarification |
| Inbox | Persistent tasks and ideas; complete/edit; date filters | Search, prioritisation, reliable reminders |
| External action | Not assumed in baseline | One approved action in one destination after feasibility check |
| Verification | Kane exercises core UI flows and feeds evidence to the coding agent | CI gates and broader regression suites |

## Scope decision still open

**A — organise commitments:** deliver capture → review → persistent inbox. Kane participates in the development loop from the first working slice.

**B — execute approved actions:** add a browser runner that creates one task in one chosen external task board and verifies the result. Destination, authentication feasibility, and reliable duplicate handling must be proven before committing to B. It is not an unrestricted browser assistant.

The architecture supports both. The baseline remains useful if the browser integration is deferred.

## Review pack

- [Product scope and acceptance criteria](docs/product-scope.md)
- [Architecture and diagrams](docs/architecture.md)
- [API and data contracts](docs/contracts.md)
- [Delivery plan and team split](docs/delivery-plan.md)
- [Open decisions for our review](docs/review-checklist.md)
- [Hackathon requirements and sources](docs/hackathon.md)
- [Initial evaluation cases](tests/evals/cases.json)

## Proposed stack and credentials

React + TypeScript frontend; FastAPI backend; SQLite and local audio storage for a single-user prototype. A persisted jobs table and one worker handle model calls. Move to PostgreSQL/object storage when deployment needs justify it.

Groq is the initial proposed hosted provider for transcription and action extraction. Local adapters can use faster-whisper and Ollama. Model IDs are configurable and must be checked at implementation time. Browser recording requires no paid API.

Kane/TestMu credentials are required for hackathon verification. A Groq key is optional if local models are used. External service OAuth credentials are required only if an API integration is chosen; browser execution instead needs an authenticated session. Secrets stay server-side and out of Git.

## Running it

This repository currently contains design documents and evaluation examples only. There is no runnable application or passing Kane suite yet. The implementation milestone is a one-command start with documented prerequisites and an accessible demo; local model downloads must not block reviewers.

## Contributing

Start with the review checklist, agree on A or B, and pick the first vertical slice. Suggested responsibilities are in the delivery plan. Do not commit real recordings, credentials, browser sessions, or personal task data. License choice remains open; no open-source license has been selected yet.
