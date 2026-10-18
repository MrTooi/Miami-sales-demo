# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-17 ~07:00 UTC.** Every fact below was read from the GitHub API (issues, PRs, comments, Actions runs and artifacts) or from `main` at `b1cee92` at that time, unless it is marked **[unverified]**.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins — say so in your handoff and refresh this file in a docs-only PR. Evidence lives in the linked issues and runs; this file only points to it.

## Governance state

- **Supervised Ledger product work is authorized (D-003, 2026-10-17):** the pilot MVP scope only, with independent review and owner merge approval on every PR. The #11/#69 gate (plus #35) now controls **unattended** agents only. Weekly plan: #92.
- Unattended Agent OS execution is disabled by default (`LEDGER_AGENT_OPERATOR_ENABLED`, `LEDGER_AGENT_EXECUTOR_ENABLED`). Enabling it is governed by the separate Issue #35 gate (`docs/AGENT_OPERATOR.md`).
- `.github/workflows/claude.yml` runs only for `github.actor == 'MrTooi'` with an `@claude` mention. The Claude GitHub App token cannot push `.github/workflows/` changes. Its own replies on #69 (2026-10-16 22:05 UTC) and #87 report the push refusal ("without workflows permission"). Workflow changes need a person or integration with workflow-write permission.

## Readiness gate (#11 / #69)

Recorded on #11 as satisfied or materially complete:
- Execution workbench trials #25–#28 (draft PRs #39, #62, #63, #64 intentionally unmerged) and human-stop proof #29.
- Hardening plateau: two consecutive PASS rounds against `c1fbbbf` (2026-10-16).

Still outstanding:
- Three genuine schedule-originated blind suites A → B → C, each ≥95%, all critical cases passing, zero critical safety violations, aggregated by `agent_evals/final_readiness.py`.
- Publish verified evidence on #11, retire the temporary readiness carrier job, then **wait for explicit owner approval**.

Genuine scheduled Suite A attempts (carrier `.github/workflows/agent-operator.yml` → core `.github/workflows/agent-final-readiness-core.yml`):

| Run | Created (UTC) | Commit | Result |
|---|---|---|---|
| `38986734588` | 2026-10-17 00:31 | `3b1a69c` | **FAIL 12/18**, **0 critical safety violations**. Failure classes posted on #69. Hardening followed in PR #83. |
| `39004751833` | 2026-10-17 05:01 | `b1cee92` | **FAIL 13/18**, **0 critical safety violations**. Failed critical cases: `a04`, `a05`, `a07`, `a11`; also failed: `a06`. Evidence artifact preserved. |
| `39007805131` | 2026-10-17 05:51 | `b1cee92` | Correctly refused: same-commit paid retry barrier in `prepare`. No model call. |

- A→B→C has **zero** successes. The next Suite A attempt needs a new reviewed change to a blind instruction input (owner-scoped hardening task); see #69.
- Scheduled Operator runs arrive irregularly: two arrived about 50 minutes apart, after a ~4.5-hour gap. Cron is every 5 minutes; delivery is best-effort. Do not substitute manual runs.

## Open work map

| Ref | Type | State at snapshot |
|---|---|---|
| #11 | Issue | Open — umbrella readiness gate |
| #35 | Issue | Open — Agent OS hardening gate before unattended scheduling |
| #69 | Issue | Open — Suite A failed twice (see above) |
| #74 | Issue | Open — Commercial Reality Gate (separate from readiness) |
| #75 | Issue | Open — Real Business Discovery Gate (separate) |
| #79 / #80 | Issue / PR | Open — Command Center. PR #80 head `933f801` merges current `main` and fixes the multi-line cron BLOCK; latest `@claude` review: PASS WITH WARNINGS. Needs owner merge approval. |
| #81 | Issue | Open — Oct 17 demo; runbook merged (PR #82). Rehearsal checklist not recorded as done. |
| #84 | Issue | Open — production exact-time scheduler design (post-gate; does not replace #69's `event=schedule` requirement) |
| #86 | Issue | Open — full-system audit: PASS WITH WARNINGS (H1, H2, M1–M7) |
| #87 / #91 | Issue / PR | Open — audit remediation wired into the readiness core. `@claude` review: PASS WITH WARNINGS, with W1–W4 fixed. Needs independent (ChatGPT/owner) review and owner merge approval. Merge it before the next paid Suite A attempt. |
| #88 / #89 / #90 | Issues / PR | Open — leadership transfer and context pack. PR #90 is this operating layer; it closes #88 and #89 on merge. |
| #67, #70 | Draft PRs | Open — older readiness drafts. #69 says it replaces #67's heartbeat approach. #70's relationship to the merged PR #71 harness was not reviewed for this snapshot. Close only with owner approval. |

## Demo state (#81)

`docs/DEMO_RUNBOOK_2026-10-17.md` defines the fictional-data demo (Overview, Costs, Transactions, Data health; `DEMO SAMPLE` label). The #86 audit found no demo blockers by static review. **[unverified]** No end-to-end rehearsal is recorded.

## Immediate next actions (at snapshot)

1. Owner/ChatGPT review and owner merge decisions for PR #90, PR #91 and PR #80.
2. Owner decision on the next Suite A hardening round (a blind-input change is required before any new paid attempt). Merge PR #91 first so the attempt runs under the hardened gate.
3. Keep waiting for genuine scheduled A→B→C. No manual substitutes.
