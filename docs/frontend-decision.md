# Frontend decision: Gradio Blocks

Decision date: 14 November 2026. Selected for the first implementation after comparing the actual product needs. This is a documentation-based choice, not a completed runtime benchmark.

## Priorities

Deliver voice/text capture, optional clarification, editable steps, explicit approval, durable task state and grounded chat within the event window. Keep Python logic understandable and reusable for a longer-term project. Precise styling and advanced board interactions are secondary for Phase A.

| Candidate | What works well here | Cost or limitation | Decision |
|---|---|---|---|
| Gradio Blocks | Microphone audio, chat components, explicit event handlers, custom compositions in Python | Dynamic business-app layouts need discipline; session state is not persistence; queue is not durable | Select for Phase A |
| Streamlit | Built-in recording/chat, fast Python UI, forms and fragments | Default reruns require careful control of side effects and draft state | Viable; fewer advantages for this event-oriented workflow |
| NiceGUI | Flexible app layouts, event handlers, FastAPI integration | Recording requires a browser integration/custom component check; more work before the main voice flow | Strong later candidate if layout needs outgrow Blocks |
| FastAPI + templates | Full control of routes and browser behaviour | Manual recording, UI updates and form wiring increase initial work | Retain as a future option, not the initial stack |

These fit judgments are engineering assessments, not measured performance rankings. Gradio is not limited to model demos; Blocks supports composed applications. Streamlit can handle this workflow correctly using forms/fragments; reruns are a trade-off, not a disqualification. NiceGUI's audio playback component should not be mistaken for a built-in microphone recorder.

## Why this choice

Gradio removes work from the core voice/chat path while explicit button and change events fit review and approval. Use one application with plain Python services and SQLite. Do not add a separate FastAPI server solely because earlier docs proposed REST endpoints. Codex can implement all candidates; the choice is driven by development scope and maintenance, not an assumed coding-agent preference.

## Constraints we accept

Use conventional controls and simple lists/editors rather than pixel-perfect custom cards. Separate temporary UI state from durable records. Explicitly configure queue/concurrency behaviour, bound provider calls, and validate state revisions. Keep framework objects out of planning and persistence modules. Public deployment needs access control and protected mutation paths. Browser audio still requires permissions and a suitable secure context.

## Revisit when

If essential recording/editing/Kane interactions cannot be made reliable in the first slice, revisit the choice with measured evidence. If later UX requires a persistent highly customised mobile shell or complex board interactions, evaluate NiceGUI or a dedicated frontend while retaining services and storage. Do not schedule a rewrite merely because a framework is associated with demos.

## Official sources checked

- [Gradio Blocks](https://gradio.app/docs/gradio/blocks): composition and events.
- [Gradio Audio](https://gradio.app/docs/audio): microphone input and audio handling.
- [Gradio State](https://gradio.app/docs/gradio/state): session lifetime and events.
- [Streamlit execution flow](https://docs.streamlit.io/develop/api-reference/execution-flow): reruns, forms, fragments.
- [Streamlit session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state): session-bound state.
- [Streamlit audio input](https://docs.streamlit.io/develop/api-reference/widgets/st.audio_input): recording widget.
- [NiceGUI foundations](https://nicegui.io/documentation/section_foundations): FastAPI integration.
- [NiceGUI audio](https://nicegui.io/documentation/audio): playback component.
- [NiceGUI events](https://nicegui.io/documentation/section_action_events): event handling.

No package version is pinned by this document. Pin after the actual compatibility spike and record the results.
