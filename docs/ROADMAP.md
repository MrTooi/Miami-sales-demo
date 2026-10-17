# Roadmap

Source-of-truth roadmap structure. It references existing GitHub issues instead of duplicating them; the issues hold the acceptance criteria and evidence. Keep it concise and change scope only with the human owner's approval.

## Current phase

**Readiness hardening + audit remediation + demo/observability support only. Product implementation is PAUSED.**

Resuming LEDGER / Opportunity Radar product work requires the Issue #11 / Issue #69 readiness gate to be satisfied **and** explicit human approval, recorded as a new entry in `docs/DECISIONS.md`.

## Now (authorized)

| Workstream | Issue / PR | Notes |
|---|---|---|
| AI team readiness gate | #11 | Umbrella gate. Workbench and plateau criteria recorded there. |
| Final scheduled blind suites A→B→C | #69 | Only genuine `event=schedule`, `run_attempt=1` runs count. No manual substitutes. |
| Full-system audit and remediation | #86 → #87 | Readiness availability/provenance fixes; workflow wiring needs workflow-write access and independent review. |
| Owner Command Center (internal, read-only) | #79 / PR #80 | Must never self-certify readiness or show a false green. |
| Oct 17 demo readiness | #81, `docs/DEMO_RUNBOOK_2026-10-17.md` | Existing functionality and fictional data only. |
| Leadership transfer + context pack | #88, #89 | This operating layer. |
| Agent evaluation upkeep | `docs/AGENT_EVALUATION.md`, `agent_evals/` | No changes to final-suite prompts/rubrics/thresholds. |

## Next after gate (not started, not authorized)

Requires readiness + explicit owner approval. Order to be confirmed by the owner.

- Commercial Reality Gate — #74 (is Ledger truthful, useful, and worth paying for?).
- Real Business Discovery Gate — #75 (can Ledger obtain and verify the data it needs from messy real businesses?).
- Production-grade exact scheduler design — #84 (GitHub cron is not an exact-time scheduler).
- Opportunity Radar evidence store / import pipeline — `PROJECT_BRIEF.md` "Immediate technical milestone" (paused product work).

## Separate gates (do not conflate)

- **#11 / #69** — technical readiness; prerequisite for asking to resume product work.
- **#35** — Agent OS hardening gate required before *unattended* executor/operator scheduling is enabled. Passing #11/#69 does not enable unattended scheduling.
- **#74 / #75** — commercial and discovery gates; technical readiness never satisfies them.

## Later

Unscheduled. Anything not listed above needs a new issue and owner prioritization first.

## Related documents

`PROJECT_BRIEF.md`, `PRODUCT_PLAN.md`, `LAUNCH_RISK_REGISTER.md`, `docs/PROJECT_CONTEXT.md`, `docs/CURRENT_STATE.md`, `docs/LEADERSHIP_MODEL.md`, `docs/DECISIONS.md`.
