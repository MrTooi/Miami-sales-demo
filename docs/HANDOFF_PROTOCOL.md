# Handoff Protocol (Claude Code ↔ ChatGPT via GitHub)

Neither assistant can see the other's private conversation. Everything needed to continue or review work must be in GitHub (issues, PRs, comments, docs, CI). This extends the handoff contract in `AGENTS.md`.

## Every handoff includes

1. **Goal** — the outcome requested or completed.
2. **Scope** — what is in and explicitly out.
3. **Changed files** — list, with anything deliberately untouched.
4. **Tests / CI** — commands run and actual results; say plainly what was not run or is pending.
5. **Risks / unknowns** — including security and data-integrity implications.
6. **Decisions needed** — and from whom (human, ChatGPT, Claude).
7. **Next action** — owner and step.

## Review comments

Label every finding:

- **BLOCKER** — must be fixed (or refuted with evidence) before the work advances.
- **WARNING** — worth addressing; does not block on its own.

Include evidence (file/line, test output, or repro). Verdict is PASS or FAIL with the blockers listed. A reviewer who changes the author's code must leave a GitHub-visible reason.

## Rules

- Do not claim a test, review, or deployment happened unless it did.
- High-risk work (finance, security, readiness, deployment, customer data) needs an independent reviewer other than the author before merge, plus human approval where `AGENTS.md` requires it.
- Record durable outcomes in `docs/DECISIONS.md`; keep `docs/ROADMAP.md` current.
