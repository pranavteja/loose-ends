# Hackathon alignment

Sources reviewed on 14 November 2026:

- [Original Kane Luma brief](https://luma.com/kanecli-online-hackathon)
- [Kane companion site](https://www.kaneclihack.sh/)
- [Kane documentation](https://www.testmuai.com/support/docs/kane-cli-introduction/)
- [Bolna inspiration](https://www.bolna.ai/symphony/buildathon)
- [Groq models](https://console.groq.com/docs/models)
- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Local transcription](https://github.com/SYSTRAN/faster-whisper)
- [Ollama structured outputs](https://ollama.com/blog/structured-outputs)

The submission must work end to end, demonstrate meaningful Kane verification, and show interaction between the coding agent and Kane. Start the loop with the first working feature. Kane is used only in development verification. Application runtime remains independent of it.

Relevant lanes: apps that verify themselves and requirements-derived tests. Acceptance criteria in product-scope.md are intended to map to actual verification evidence.

Deadline: Nov 19, 2026, 23:59 IST. Fresh repository from Nov 12 onward; TestMu registration and Kane use required. Published initial allocation is 10,000 Kane credits. Confirm current limits in the account.

Official pages differ: Luma specifies three minutes and allows invited repo access/Drive; companion site specifies a public repository, YouTube, approximately 3–5 minutes, and two public posts. Conservative submission: public repository, three-minute unlisted YouTube demo, two public posts, accessible app or runnable command, setup documentation, and third-party-service fallback. Do not publish anything until the team chooses to do so.

Submission checklist:

- [ ] Account and Kane run
- [ ] Real app and agent/Kane feedback evidence
- [ ] Setup instructions and reviewer access
- [ ] Three-minute video
- [ ] Project paragraph and repository link
- [ ] Two public project posts
- [ ] Deadline and exact submission destination checked again

Bolna is inspiration only; its submissions are closed. No Bolna service dependency is assumed.

## Verification mapping

| Kane flow to implement | Acceptance criteria | Expected evidence |
|---|---|---|
| Type thought, skip question, edit steps, approve | AC07–AC11 | Saved task and steps survive refresh |
| Correct transcript before approval | AC05, AC12 | New draft reflects correction; old approval rejected |
| Retry approval after simulated lost response | AC10 | Exactly one saved task |
| Ask bot about an existing task | AC14–AC15 | UI references actual task without changing it |

Use separate model evaluations for semantic quality and audio accuracy; a green UI flow does not prove either. Record a real development change, Kane result and agent response. Do not fabricate a caught bug or passing run. Scripts and evidence will live under verification/kane/ when implemented.
