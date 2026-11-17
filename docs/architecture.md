# Architecture — voice-first local application

This document describes the implemented direction as of 17 November 2026. The browser has one product shell; Talk, Review, and Board are views within it rather than separate websites.

## Runtime shape

```mermaid
flowchart LR
    B["Browser: Talk / Review / Board"] <-->|"WebRTC microphone + agent audio"| LK["LiveKit Cloud"]
    A["Python voice agent"] <-->|"Room audio + internal model text"| LK
    A <-->|"Whisper + OSS 20B"| G["Groq API"]
    A <-->|"streaming Cartesia TTS"| I["LiveKit Inference"]
    B <-->|"Token + draft/task JSON"| W["Local FastAPI :7861"]
    W <-->|"Validated service calls"| S["Python application services"]
    A -->|"Create review draft only when asked"| S
    S <-->|"Captures, proposals, tasks, steps"| D["SQLite"]
```

Two local processes are required:

- `python app.py` serves the UI and local API on port 7861.
- `python -m loose_ends.voice_agent start` joins dispatched LiveKit rooms and runs the conversation.

LiveKit transports real-time media and provides streaming Cartesia speech through LiveKit Inference. Groq provides Whisper speech-to-text and OSS 20B reasoning. The agent publishes generated speech into the room as WebRTC audio. Talk never renders the model text as chat.

## Product journey

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Browser shell
    participant V as Voice agent
    participant S as Application service
    participant D as SQLite
    U->>UI: Start talking
    UI->>V: LiveKit microphone audio
    V-->>UI: Spoken conversational reply
    U->>V: "Make a draft"
    V->>S: Create persisted proposal
    S->>D: Save draft and source context
    U->>V: "Actually, change it to Friday"
    V->>S: Revise the same pending capture
    S->>D: Supersede old proposal; save current draft
    UI->>S: Refresh Review count
    U->>UI: End conversation
    UI->>S: Load drafts
    UI-->>U: Open Review automatically
    U->>UI: Edit and approve
    UI->>S: Approve proposal
    S->>D: Transaction: task, steps, approval
    UI-->>U: Open Board
```

The model may discuss and refine freely, but it creates a persisted proposal only after an explicit drafting request. After that, an explicit spoken correction can revise the same capture and supersede its earlier proposal. A proposal is not a task. Approval is the boundary that creates board state.

## Modules and responsibilities

| Module | Responsibility |
|---|---|
| `voice-ui/` | Responsive shell, Talk/Review/Board navigation, LiveKit browser client, voice states, room audio, API rendering. |
| `voice_server.py` | Static files, health/token routes, review and board JSON routes; no business rules in the browser. |
| `loose_ends/voice_agent.py` | Turn detection, Groq Whisper, OSS 20B conversation, and guarded draft create/revise tools. |
| `loose_ends/services.py` | Validation, proposal lifecycle, approval idempotency, task and step state. |
| `loose_ends/database.py` | SQLite schema and transactional connections. |
| `loose_ends/groq_adapter.py` | Structured planning and task-aware model requests used by application services. |

## UI state model

Talk is the default route. Navigation uses `#talk`, `#review`, and `#board`, so reloads preserve the current place without requiring server-side routes.

- **Talk** keeps LiveKit room and remote-audio state in the browser; it does not render or retain a chat transcript.
- **Review** always reloads durable draft proposals from `/api/review`.
- **Board** always reloads durable tasks and steps from `/api/board`.
- The Review badge and Talk handoff card are derived from the same proposal list.
- Ending a room refreshes proposals; Review opens when at least one exists.
- Spoken corrections revise the active pending draft and the Review badge continues to represent its current version.
- If no draft exists, the Talk view remains visible and explains that the user should say “make a draft” next time.

## Data and safety boundaries

Captures, proposals, tasks, and steps live in SQLite. Approval writes the task, ordered steps, receipt, and proposal status in one transaction. A unique proposal-to-task relationship makes repeat approvals safe. Missing dates remain missing; the model must not invent completion or claim an external action happened.

The local token endpoint signs short-lived, opaque LiveKit identities. Provider and LiveKit secrets stay in `.env` and server processes. The app binds to loopback by default. A public deployment requires access control, secure cookies/tokens, TLS, per-user ownership, and a review of audio retention.

## Failure behaviour

| Failure | Expected experience |
|---|---|
| Voice setup missing | Start shows a clear configuration message; Review and Board remain usable. |
| Agent slow to join | The voice session panel says it is waiting; connection state stays visible. |
| Groq turn fails | Agent explains the failure; the room can continue or be restarted. |
| Draft refresh fails | Existing conversation remains; a toast reports the local API error. |
| Approval conflicts | No duplicate is created; Review reports the conflict and reloads. |
| Streaming TTS fails | The agent reports the provider error in the local transcript and sends an actionable status to Talk. Review and Board remain usable. |

## Growth triggers

| Trigger | Change to consider |
|---|---|
| Several users or public access | Authentication, per-user records and rooms, PostgreSQL. |
| Work must continue after process exit | Durable job queue and processing-status API. |
| Faster turn recognition is essential | True streaming STT provider behind the same voice-only interface. |
| Speech usage exceeds the development allowance | Add a LiveKit billing plan or configure another streaming TTS provider behind the same audio output. |
| External calendar/task actions are added | OAuth, explicit proposed-change review, and integration audit log. |

The retired Gradio UI and dependency have been removed and are not part of this diagram.
