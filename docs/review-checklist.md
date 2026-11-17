# Remaining review decisions

## Confirmed direction

- The real-time voice experience is the product home.
- Talk, Review, and Board share one responsive browser shell and port.
- LiveKit provides WebRTC transport; Groq Whisper and OSS 20B provide intelligence.
- Draft creation is explicit and every draft requires approval.
- Python services and SQLite remain independent of the frontend.
- No computer-use agent, external task mutation, calendar write, or reminder claim.

## Product decisions still open

- [ ] Choose how long source audio/transcripts should be retained.
- [ ] Decide whether browser speech quality is sufficient for the intended demo devices.
- [ ] Decide whether lower-latency streaming STT is needed even though Talk does not display captions.
- [ ] Confirm the default timezone and how users will change it.
- [ ] Decide when completed/cancelled work should be archived or hidden.
- [ ] Confirm repository visibility, collaborator access, and license.

## Verification before a public demo

- [ ] Test microphone permission, interruption, and browser speech on the target laptop.
- [ ] Test one mobile browser at narrow width.
- [ ] Verify “make a draft” reliably creates one proposal and updates the Review badge.
- [ ] Verify a spoken correction supersedes that proposal instead of adding a duplicate draft.
- [ ] Verify ending with a draft opens Review; ending without one gives useful guidance.
- [ ] Verify edited approval reaches Board and repeat approval cannot duplicate it.
- [ ] Restart both processes and confirm drafts, tasks, and step progress persist.
- [ ] Use synthetic data and confirm no secret appears in built browser assets or logs.

Existing decisions should only be reopened when testing reveals a concrete constraint.
