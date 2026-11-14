# Remaining review decisions

## Confirmed direction

- Home-screen companion, optional clarification and essential substeps.
- Internal task board; Phase A first, Phase B later.
- No computer-use agents or runtime browser runner.
- Gradio Blocks with independent Python services and SQLite initially.
- Kane separated from application runtime.
- Documentation teaches through problems, requirements and modules.

## Proposed defaults to review

- [ ] Start with one focused clarification per round and allow skipping; cap rounds at two for MVP.
- [ ] Show ordered steps, with no nested subtasks or automatic schedule optimisation.
- [ ] Default timezone Asia/Kolkata, editable; never infer a missing deadline.
- [ ] Confirm the desktop split view and mobile Bot/Board navigation in wireframes.
- [ ] Choose audio retention duration; review delete-source/retain-task policy.
- [ ] Choose local single-user setup or restricted hosted demo.
- [ ] Confirm actual combined availability and responsibilities with the colleague.
- [ ] Confirm Groq access and model availability; local models remain an optional adapter.
- [ ] Select repository host, visibility, collaborator access and license.

## Technical checks before promising a demo

- Kane can reach the development app and return evidence to the coding agent.
- Browser recording works on the target laptop and phone.
- Provider responses validate for clarification and substeps.
- Request timeout/retry behaviour preserves input and avoids stale writes.
- Persistence survives restart and deployment storage is not ephemeral.

Keep further comments here or inline with `>>`. Existing decisions need not be reopened unless a concrete constraint changes.

- [ ] Validate microphone, editable steps, session restoration and Kane interaction in the first Gradio slice.
