# Decision Log

Lightweight ADR-style log. Append new entries at the bottom; do not rewrite accepted entries (supersede them instead).

## Template

```
### D-NNN — Title
- Date:
- Status: Proposed | Accepted | Superseded by D-NNN
- Decided by:
- Context:
- Decision:
- Consequences / risks:
- Evidence / links (issues, PRs):
```

## Decisions

### D-001 — Transfer Ledger technical leadership to Claude Code
- Date: 2026-10-17
- Status: Accepted (takes effect when the PR implementing Issue #88 is approved and merged by the human owner)
- Decided by: Human owner (Issue #88)
- Context: The operating model needs a repo-local, GitHub-visible definition so that Claude Code and ChatGPT can work from shared state rather than private conversation history.
- Decision: Claude Code is the primary technical lead for authorized engineering work. ChatGPT is product/strategy/architecture/independent-review support. The human owner keeps final authority. Claude is never the sole reviewer of its own high-risk changes. Claude Code runs only when triggered by tasks, events, or schedules.
- Consequences / risks: Documentation and instructions only. Autonomy is limited to what is authorized; see `docs/LEADERSHIP_MODEL.md`.
- Evidence / links: Issue #88, Issue #89; `CLAUDE.md`; `docs/LEADERSHIP_MODEL.md`.

### D-002 — Readiness gates unchanged; product stays paused
- Date: 2026-10-17
- Status: Accepted
- Decided by: Human owner (Issue #88)
- Context: Leadership transfer must not alter readiness semantics.
- Decision: Readiness gates, rubrics, scorer thresholds, model configuration, and workflow logic are unchanged. Product implementation remains PAUSED until Issue #11 / Issue #69 readiness is satisfied and the human owner explicitly approves resuming (to be logged as a new decision).
- Consequences / risks: Only readiness hardening, demo/observability support, and explicitly assigned work proceed.
- Evidence / links: Issue #88, Issue #11, Issue #69.
