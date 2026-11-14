# Review checklist

Please annotate this file or open issues once a remote repository exists.

- [ ] Working name: keep Loose Ends or rename?
- [ ] First user and recurring use case: personal capture, work follow-up, or both?
- [ ] MVP A (inbox) or B (one external browser action)?
- [ ] If B: which destination and exact operation? Who supplies a test account?
- [ ] Groq first, local first, or selectable? Which machine will run local inference?
- [ ] Agree React/FastAPI and SQLite baseline, or propose an alternative with a reason.
- [ ] Who owns frontend, backend, model evaluation, deployment, and Kane flows?
- [ ] Agree date ambiguity policy and default timezone.
- [ ] Agree audio retention and capture deletion behaviour.
- [ ] Restricted single-user demo or authenticated personal deployment?
- [ ] Choose repository host/account, visibility, license, and collaborator access.
- [ ] Confirm actual hours available before Nov 19; cut scope accordingly.

Open technical questions: Kane connectivity to local deployment; programmatic result format; destination login/session support; audio format compatibility on target phone; provider availability; worker recovery after restart.

The next implementation task after review is the text-to-inbox vertical slice, not building all planned components at once.
