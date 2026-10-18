# Roadmap

Source-of-truth roadmap structure. It references existing GitHub issues instead of duplicating them; the issues hold the acceptance criteria and evidence. Keep it concise and change scope only with the human owner's approval.

## Current phase

**Supervised build of the Ledger pilot MVP (D-003)**, with readiness hardening in the background. Unattended agents stay disabled until A/B/C and #35 pass and the owner approves.

Scope and limits: D-003 in `docs/DECISIONS.md`. The weekly plan lives in the current weekly checklist issue (Oct 19–25: #92).

## Now (authorized)

| Workstream | Issue / PR | Notes |
|---|---|---|
| **Ledger pilot MVP** | D-003, #92 | Data import + what's-missing report → profit by job/customer → money-leak report → weekly owner summary → pilot data-safety minimums. Small PRs, independent review, owner merge approval. |
| Customer evidence (partner lane) | #30, #92 | Target customer type, interviews, willingness to pay, a pilot candidate. The partner leads; evidence shapes MVP priorities. Collecting evidence is authorized now; formal #74/#75 claims are not (see below). |
| AI team readiness gate | #11 | Gates **unattended** agents only. Workbench and plateau criteria recorded there. |
| Final scheduled blind suites A→B→C | #69 | Only genuine `event=schedule`, `run_attempt=1` runs count. No manual substitutes. |
| Full-system audit and remediation | #86 → #87 → PR #91 | Readiness availability/provenance fixes wired into the core; needs independent review and owner merge approval. |
| Owner Command Center (internal, read-only) | #79 / PR #80 | Must never self-certify readiness or show a false green. |
| Oct 17 demo readiness | #81, `docs/DEMO_RUNBOOK_2026-10-17.md` | Existing functionality and fictional data only. |
| Leadership transfer + context pack | #88, #89 → PR #90 | This operating layer. |
| Agent evaluation upkeep | `docs/AGENT_EVALUATION.md`, `agent_evals/` | Only when the owner explicitly scopes the task; no final-suite prompt/rubric/threshold changes unless specifically approved. |

## Next (not yet authorized; each needs an owner decision)

- Commercial Reality Gate — #74. Its acceptance criteria are **not** deferred or waived: no pilot-ready or commercially-validated claim until they are met.
- Real Business Discovery Gate — #75. Its acceptance criteria are **not** deferred or waived; messy real-data discovery must be proven before a pilot is called ready.
- Production-grade exact scheduler design — #84 (GitHub cron is not an exact-time scheduler).
- Opportunity Radar evidence store / import pipeline (`PROJECT_BRIEF.md` milestone), when the owner assigns it.
- Live provider integrations (QuickBooks/Square/bank APIs) with real credentials.
- Unattended agent execution, after A/B/C + #35 + owner approval.

## Separate gates (do not conflate)

- **#11 / #69**: AI-team readiness; gates **unattended** agent execution (with #35). It does not gate supervised product work (D-003).
- **#35** — Agent OS hardening gate required before *unattended* executor/operator scheduling is enabled. Passing #11/#69 does not enable unattended scheduling.
- **#74 / #75** — commercial and discovery gates; technical readiness never satisfies them.

## Later

Unscheduled. Anything not listed above needs a new issue and owner prioritization first.

## Related documents

`PROJECT_BRIEF.md`, `PRODUCT_PLAN.md`, `LAUNCH_RISK_REGISTER.md`, `docs/PROJECT_CONTEXT.md`, `docs/CURRENT_STATE.md`, `docs/LEADERSHIP_MODEL.md`, `docs/DECISIONS.md`.
