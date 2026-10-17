# Current State — SNAPSHOT (stale-able)

**Snapshot date: 2026-10-17.** Written from the contents of `main` at commit `b1cee92` (Merge PR #85) and from the issue-number list in Issue #89 as written by the owner.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub (open issues, open PRs, CI on `main`, labels) and from `main` itself. If anything here disagrees with live GitHub or `main`, GitHub/`main` wins. Update this file (docs-only PR) when you find it stale.

## How each statement was sourced

- **[main]** verified by reading files on `main` at `b1cee92`.
- **[issue #89]** taken from the owner's issue text. **Not independently verified against live GitHub** in the session that wrote this file, because `gh`/`git fetch` were not permitted there. Re-check before relying on it.
- **[unknown]** not known. Follow the linked issue.

## Governance state

- **Product implementation is PAUSED** until Issue #11 / Issue #69 technical readiness requirements pass **and** the human owner explicitly approves resuming. [issue #89]
- Final readiness requires genuine **schedule-originated A -> B -> C** blind suites with strict evidence/provenance. Manual dispatches/reruns must not be counted. [issue #89]
- Agent OS unattended execution is **disabled**; `LEDGER_AGENT_OPERATOR_ENABLED` and `LEDGER_AGENT_EXECUTOR_ENABLED` must not be set true without the readiness gate and explicit human authorization. Claude is on-demand only. [main: `docs/AGENT_OPERATOR.md`]
  - Note: that doc cites the readiness gate as Issue #35, while Issue #89 cites #11 / #69. **Unreconciled; confirm against live GitHub.** [unknown]
- `.github/workflows/claude.yml` only runs when `github.actor == 'MrTooi'` and `@claude` is tagged. [main]
- Technical readiness is separate from the commercial gate (#74) and the discovery gate (#75). [issue #89]

## Issue / PR map (as of snapshot)

Status columns are from Issue #89 unless marked. Verify live.

| Ref | Subject | Snapshot note |
|---|---|---|
| #11 | AI team readiness gate | Active; blocks resuming product work |
| #69 | Final scheduled blind A/B/C readiness gate | Active |
| #74 | Commercial Reality Gate | Active; separate from technical readiness |
| #75 | Real Business Discovery Gate | Active; separate from technical readiness |
| #79 / #80 | Ledger Command Center owner observability | PR #80 reportedly had required fixes/review on truthful schedule parsing and false-green avoidance; current status [unknown] |
| #81 | Oct 17 demo readiness/runbook | Runbook exists on `main`: `docs/DEMO_RUNBOOK_2026-10-17.md` [main] |
| #84 | Production exact scheduler architecture/design | Separate from the GitHub readiness cron. GitHub cron is **not** production exact scheduling |
| #85 | Readiness carrier schedule resilience | Merged; is the latest commit on `main` [main] |
| #86 | Full-system Claude audit | PASS WITH WARNINGS, with remediation items |
| #87 | Audit remediation | Partial Claude branch reportedly exists; live workflow wiring and safe completion still matter; status [unknown] |
| #88 | Leadership transfer to Claude Code | Defines `CLAUDE.md` plus `docs/LEADERSHIP_MODEL.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`. **Those files are not on `main` at the snapshot.** [main] |
| #89 | This context pack | In progress via its own PR |

## Readiness carrier (read the code before acting)

At snapshot, `.github/workflows/agent-operator.yml` is the scheduled/manual planner with cron entries, and `.github/workflows/agent-final-readiness-core.yml` is the readiness core. The issue says the carrier calls the core; read both workflows and `tests/test_readiness_carrier_cadence.py` / `tests/test_agent_scheduled_readiness*.py` on current `main` before acting. [main, partially verified]

## Demo state

- Runbook: `docs/DEMO_RUNBOOK_2026-10-17.md`. Fictional sample data; `DEMO SAMPLE` should be visible; tabs Overview, Costs, Transactions, Data health; scope frozen (no new financial/product behavior for the demo). [main]
- Whether the demo acceptance checklist has been completed is [unknown]. Its boxes are unchecked in the runbook.

## Authorized work right now

- Only what the owner has explicitly authorized in a GitHub issue/comment. At snapshot: governance, readiness, audit remediation, observability, demo reliability, and documentation work listed above. **No new product features.** [issue #89]
- Docs-only context work such as this pack is authorized by Issue #89.

## Known blockers (at snapshot)

- Readiness gate (#11 / #69) not passed [issue #89]. Verify live; do not assume.
- Commercial (#74) and discovery (#75) evidence not established [issue #89].
- Audit remediation (#87) incomplete [issue #89].
- Leadership-transfer files from #88 not yet on `main` [main].

## Suggested next actions (verify first)

1. Refresh live state: open issues/PRs, CI on `main`, review comments on PR #80 and the #87/#88 branches.
2. Land #88 and this #89 pack (docs-only, human-approved merge).
3. Continue the highest-priority *authorized* item from #11/#69, #80, #87, #84. Ask the owner when priority is unclear.
4. Do not resume product feature work without explicit owner approval.

## Open ambiguities for the owner

- Readiness-gate issue number: #35 (in `docs/AGENT_OPERATOR.md`) vs #11 / #69 (Issue #89).
- Whether `CLAUDE.md` and the #88 docs are on a branch/PR that this pack should merge into, or on `main` already.
