# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-17 ~02:30 UTC**, verified against live GitHub (issues, PRs, Actions run history) and `main` at `b1cee92` (Merge PR #85).

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins — say so in your handoff and refresh this file in a docs-only PR. Evidence lives in the linked issues; this file only points to it.

## Governance state

- **Product implementation is PAUSED** until the #11 / #69 readiness gate is satisfied **and** the owner explicitly approves resuming. Nothing resumes automatically.
- Unattended Agent OS execution is disabled by default (`LEDGER_AGENT_OPERATOR_ENABLED`, `LEDGER_AGENT_EXECUTOR_ENABLED`). Enabling it is governed by the separate Issue #35 gate (`docs/AGENT_OPERATOR.md`).
- `.github/workflows/claude.yml` runs only for `github.actor == 'MrTooi'` with an `@claude` mention. The Claude GitHub App token **cannot write `.github/workflows/`** (observed on #69 and #87); workflow changes need an integration or person with workflow-write permission.

## Readiness gate (#11 / #69)

Recorded on #11 as satisfied or materially complete:
- Execution workbench trials #25–#28 (draft PRs #39, #62, #63, #64 intentionally unmerged) and human-stop proof #29.
- Hardening plateau: two consecutive PASS rounds against `c1fbbbf` (2026-10-16).

Still outstanding:
- Three genuine schedule-originated blind suites A → B → C, each ≥95%, all critical cases passing, zero critical safety violations, aggregated by `agent_evals/final_readiness.py`.
- Publish verified evidence on #11, retire the temporary readiness carrier job, then **wait for explicit owner approval**.

Run history:
- Carrier: `.github/workflows/agent-operator.yml` (schedule) calls the `workflow_call` core `.github/workflows/agent-final-readiness-core.yml` (PR #78).
- First genuine Suite A run `38986734588` (2026-10-17 00:31 UTC, commit `3b1a69c`): **FAIL, 12/18**, 0 critical violations, evidence artifact preserved. Failure classes are listed on #69.
- Hardening for those failure classes merged in PR #83. Carrier cadence raised to every 5 minutes in PR #85. `main` CI green on `b1cee92`.
- **As of the snapshot, GitHub has delivered no scheduled Operator run since `38986734588`.** Historically, scheduled Operator runs arrived roughly every 2–5 hours despite the 30-minute (now 5-minute) cron. A→B→C progress is bounded by GitHub schedule delivery, not by code. Do not substitute manual runs.

## Open work map (verified live at snapshot)

| Ref | Type | State at snapshot |
|---|---|---|
| #11 | Issue | Open — umbrella readiness gate |
| #35 | Issue | Open — Agent OS hardening gate before unattended scheduling |
| #69 | Issue | Open — Suite A failed once; awaiting next genuine scheduled attempt |
| #74 | Issue | Open — Commercial Reality Gate (after readiness; separate) |
| #75 | Issue | Open — Real Business Discovery Gate (separate) |
| #79 | Issue | Open — build private read-only Command Center |
| #80 | PR | Open — Command Center MVP, head `e46950f`, based on `d88f82e` (behind `main`). Latest review (Issue #86 follow-up on PR #80): **BLOCK**. The cron parser reads only the first `cron:` line, but `main` now has two. Needs a rebase onto `main`. Warnings: "ON TRACK" wording; unverified `streamlit run` import of `command_center.status_logic` |
| #81 | Issue | Open — Oct 17 demo; runbook merged (PR #82). Rehearsal checklist not recorded as done |
| #84 | Issue | Open — production exact-time scheduler design (post-gate; does not replace #69's `event=schedule` requirement) |
| #86 | Issue | Open — full-system audit: PASS WITH WARNINGS (H1, H2, M1–M7) |
| #87 | Issue | Open — audit remediation. Branch `claude/issue-87-20261017-0137` has tested helpers (`agent_evals/readiness_history.py`, instruction-hash helpers), CODEOWNERS and a docs fix, but **no workflow wiring and no PR** |
| #88 | Issue | Open — leadership transfer (this context layer) |
| #89 | Issue | Open — context pack (this context layer) |
| #67, #70 | Draft PRs | Open — older readiness drafts. #69 says it replaces #67's heartbeat approach. #70's relationship to the merged PR #71 harness was not reviewed for this snapshot. Close only with owner approval |

## Demo state (#81)

`docs/DEMO_RUNBOOK_2026-10-17.md` defines the fictional-data demo (Overview, Costs, Transactions, Data health; `DEMO SAMPLE` label). The #86 audit found no demo blockers by static review; the app was not launched in that audit.

## Immediate next actions (at snapshot)

1. Land this context layer (#88/#89) after independent review and owner approval.
2. #87: wire the remediation into the readiness core with stricter tests, open a PR, independent review, and owner-approved merge. Merging changes the commit the next paid Suite A attempt runs on.
3. PR #80: fix multi-line cron parsing, rebase onto `main`, re-review.
4. Keep waiting for genuine scheduled A→B→C. No manual substitutes.
