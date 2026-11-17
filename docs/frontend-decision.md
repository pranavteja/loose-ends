# Frontend decision: voice-first product shell

Decision date: 17 November 2026. This supersedes the 14 November Gradio decision after testing the real-time prototype. The voice interface is now the product interface, not a page embedded inside a separate review application.

## Decision

Use one responsive browser application with three persistent views:

1. **Talk** — a LiveKit conversation with live notes and typed fallback.
2. **Review** — editable drafts created during the conversation.
3. **Board** — approved tasks, ideas, steps, and completion state.

The Vite-built frontend is served by the local FastAPI process at `http://127.0.0.1:7861`. FastAPI also supplies short-lived LiveKit tokens and small JSON endpoints for drafts and board state. Plain Python services and SQLite remain the source of truth.

## Why the plan changed

The working voice prototype established the interaction quality the product needs: one tap, automatic turn-taking, interruption, visible dialogue, and a calm visual identity. Embedding that experience in Gradio created two products on one screen, duplicated navigation, and made “what happens after the conversation?” unclear.

The revised shell keeps the part that worked and removes the seams:

- no iframe and no second local URL;
- one design system and one navigation model;
- a visible Talk → Draft → Review → Board journey;
- a Review badge and “draft ready” call to action;
- ending a conversation opens Review when a draft exists;
- empty states explain the exact next action;
- secrets, persistence, and approval rules remain server-side.

## Experience principles

| Principle | UI consequence |
|---|---|
| Conversation first | Talk is the default view and the voice orb remains the main action. |
| Make the next step obvious | The page explains “say make a draft”; ending routes to Review when possible. |
| Suggestions are not commitments | Drafts are editable and never reach the Board without approval. |
| Keep context visible | Review shows the source excerpt and unresolved detail beside the proposed plan. |
| Preserve user control | Dismiss, reopen, cancel, and step-completion actions are explicit. |
| One local product | Talk, Review, Board, tokens, and persistence share port 7861. |

## Technical boundaries

- `voice-ui/` owns browser rendering, navigation, WebRTC interaction, and browser speech synthesis.
- `voice_server.py` serves the compiled assets, token endpoint, and local JSON API.
- `loose_ends/services.py` owns validation, idempotent approval, and state changes.
- SQLite is durable state; JavaScript state is presentation state only.
- The LiveKit API secret and Groq key never enter frontend code.
- The app remains loopback-only and single-user. Authentication is required before any public deployment.

## Accepted trade-offs

The dedicated frontend needs explicit HTML, CSS, and API wiring, but the implemented voice experience already required those capabilities. LiveKit adds a separate worker process, and Groq Whisper publishes a turn after the user pauses rather than word-by-word interim transcription. Browser speech quality depends on the installed browser/OS voices. These are preferable to splitting the main journey across two unrelated interfaces.

## Revisit when

- a public or multi-user deployment requires authentication and per-user room/data isolation;
- long-running planning jobs need durable workers and status polling;
- a true streaming STT provider is needed for interim word captions;
- mobile packaging requires native audio/session integration;
- browser speech quality is insufficient and a dedicated TTS provider is justified.

The old Gradio module and dependency have been removed; they are not part of the current runtime or UI plan.
