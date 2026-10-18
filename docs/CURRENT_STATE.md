# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-18 ~03:45 UTC.** Every fact below was read from the GitHub API (issues, PRs, comments, Actions runs and artifacts) or from `main` at `cc55c6a` at that time, unless it is marked **[unverified]**. D-003 itself is the owner decision recorded by PR #93; it is in force once that PR is merged with the owner's approval.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins. Say so in your handoff, and refresh this file in a docs-only PR. Evidence lives in the linked issues and runs; this file only points to it.

## Governance state

- **D-003 (owner decision, 2026-10-17; recorded by PR #93):**
  - Ledger pilot-MVP work is authorized in **supervised mode** only: every PR independently reviewed and owner-approved.
  - The #11/#69 A/B/C gate plus #35 now controls **unattended** agents only. Its criteria are unchanged.
  - The approvals are a human process, **not** machine-enforced: branch protection / required reviews are off on `main`.
- Unattended Agent OS execution is disabled by default (`LEDGER_AGENT_OPERATOR_ENABLED`, `LEDGER_AGENT_EXECUTOR_ENABLED`); #35 governs enabling it.
- `.github/workflows/claude.yml` runs only for `github.actor == 'MrTooi'` with an `@claude` mention. The Claude GitHub App token cannot push `.github/workflows/` changes (its replies on #69 and #87 report the refusal).
- Commercial (#74) and discovery (#75) gates are unchanged. Customer-evidence collection is happening now; formal pilot-ready or commercial-validation claims still need their acceptance criteria.

## Readiness gate (#11 / #69): unattended agents only

- Workbench trials #25–#28 and human-stop proof #29 are recorded on #11. The hardening plateau passed (two PASS rounds, 2026-10-16).
- Genuine scheduled Suite A attempts:
  - `38986734588` (`3b1a69c`): **FAIL 12/18**, **0 critical safety violations**.
  - `39004751833` (`b1cee92`): **FAIL 13/18**, **0 critical safety violations**. Failed critical cases: `a04`, `a05`, `a07`, `a11`; also failed: `a06`.
- PR #91 (audit remediation, #87) merged at `749d368`. Every scheduled run since (latest `39086919071`, 2026-10-18 01:33 UTC, on `cc55c6a`) refuses in `prepare` with "no qualifying reviewed hardening change". No model call is made. This is expected until an owner-approved change to a blind instruction input lands.
- A→B→C successes: **0**.

## Recently merged (2026-10-18)

| PR | What | Merge |
|---|---|---|
| #90 | Claude Code leadership + context layer (closed #88, #89) | `9dcc28c` |
| #91 | Readiness audit remediation (#87) | `749d368` |
| #80 | Internal read-only Command Center (#79) | `cc55c6a` |

## Open work map

| Ref | Type | State at snapshot |
|---|---|---|
| #93 | PR | D-003 decision record. ChatGPT: PASS WITH WARNINGS. Awaiting owner confirmation and merge approval. |
| #92 | Issue | Weekly checklist Oct 19–25 (build lane + partner customer lane) |
| #11 / #69 / #35 | Issues | Readiness gates for unattended agents (see above) |
| #74 / #75 | Issues | Commercial and discovery gates |
| #79 / #87 | Issues | Delivered by #80 / #91; left open for the owner to close |
| #81 | Issue | Oct 17 demo; runbook merged (PR #82). Rehearsal not recorded **[unverified]** |
| #84 | Issue | Production exact-time scheduler design (later) |
| #16 | Draft PR | Website (partner) |
| #39, #62, #63, #64 | Draft PRs | Workbench trial evidence, intentionally unmerged |
| #67, #70 | Draft PRs | Older readiness drafts; close only with owner approval |

## Immediate next actions

1. Owner confirms D-003 on PR #93 in their own words, then approves the merge.
2. Suite A hardening proposal on #69: owner-scoped, ChatGPT-reviewed, owner-approved.
3. Ledger MVP spec, then the first MVP PR (data import + what's-missing report), per #92.
4. Partner: customer conversations logged in the #30 format; website.
