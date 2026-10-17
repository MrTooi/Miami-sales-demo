# Context Index

One-page map of what controls what. Use it so obsolete or lower-authority files are not read as policy.

## Authority order (highest first)

1. Explicit instruction from the human owner in the current GitHub issue/comment.
2. Live GitHub state: open issues, PRs, review comments, CI results, and current `main`.
3. Policy: `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`.
4. Durable context: `docs/PROJECT_CONTEXT.md` and the `#88` docs listed below.
5. Snapshots: `docs/CURRENT_STATE.md`, dated runbooks, `PROJECT_BRIEF.md` (dated 2026-10-13).

## Files

| File | Controls | Type |
|---|---|---|
| `CLAUDE.md` | Claude Code session-start protocol | Policy (added by the Issue #88/#89 work) |
| `AGENTS.md` | Roles, routing, non-negotiable rules, definition of ready | Policy |
| `.github/copilot-instructions.md` | Repo-wide AI rules, evidence hierarchy | Policy |
| `docs/PROJECT_CONTEXT.md` | What LEDGER/Radar are, invariants, philosophy | Durable |
| `docs/CURRENT_STATE.md` | Dated status, issue/PR map, blockers | Snapshot, stale-able |
| `docs/LEADERSHIP_MODEL.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md` | Leadership split, roadmap, decision log | Issue #88; not on `main` at 2026-10-17. Read if present |
| `PROJECT_BRIEF.md` | Company goal, hypotheses, evidence hierarchy | Durable-ish, dated 2026-10-13. Its "Alex + ChatGPT / Partner + Gemini" team split and `opportunity-radar-mvp` branch note predate the Claude leadership transfer; do not treat as current |
| `LAUNCH_RISK_REGISTER.md` | P0/P1 risks before real client data | Plan, not evidence of implemented controls |
| `PRODUCT_PLAN.md` | Product plan | Check date before use |
| `opportunity_radar/README.md` | Radar architecture | Durable |
| `docs/AGENT_OPERATOR.md` | Agent OS control plane, rollout flags | Policy-adjacent; check against workflows |
| `docs/AI_TEAM.md`, `docs/AI_ENGINEERING_PIPELINE.md` | Team and pipeline design | Design |
| `docs/AGENT_EVALUATION.md`, `docs/AGENT_BEHAVIORAL_EVAL_PROTOCOL.md`, `agent_evals/` | Agent evaluation | Policy-adjacent |
| `docs/AGENT_PUBLICATION_RECOVERY.md` | Publication recovery | Operational |
| `docs/DEMO_RUNBOOK_2026-10-17.md` | Oct 17 demo script and claims to avoid | Dated runbook |
| `.github/workflows/*.yml` | Actual automation behavior | Code; read, do not edit without authorization |

## Issues (verify live before use)

| Ref | Controls |
|---|---|
| #11 | AI team readiness gate |
| #69 | Final scheduled blind A/B/C readiness gate |
| #74 | Commercial Reality Gate |
| #75 | Real Business Discovery Gate |
| #79 / #80 | Command Center owner observability (issue / PR) |
| #81 | Oct 17 demo readiness |
| #84 | Production exact scheduler design |
| #85 | Readiness carrier resilience (merged) |
| #86 | Full-system audit |
| #87 | Audit remediation |
| #88 | Leadership transfer to Claude Code |
| #89 | This context pack |

Which of #79/#80/#87/#88 are issues vs PRs was not verified in the session that wrote this index; check each.
