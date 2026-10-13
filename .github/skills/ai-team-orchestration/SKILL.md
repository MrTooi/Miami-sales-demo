---
name: ai-team-orchestration
description: Coordinate the LEDGER/Opportunity Radar AI team across planning, implementation, independent QA, security review, CI, human approval, and durable project context.
---

# AI Team Orchestration

Use this skill for multi-step work that benefits from specialist ownership or independent review.

## Team

- `LEDGER Orchestrator` — scope, sequencing, acceptance criteria, handoffs, context.
- `Backend Engineer` — core logic, persistence, scoring, data models, APIs.
- `Integrations Engineer` — providers, OAuth, syncs, imports, retries, reconciliation boundaries.
- `QA Critic` — independent behavioral verification and regression challenge.
- `Security & Data Integrity` — trust boundaries, secrets, tenant isolation, tool governance, provenance.

## Default flow

`Plan -> Implement -> self-review -> QA -> security review when risk requires -> CI -> human approval when required -> merge -> update context`

Keep process proportional.

### Use parallel work only when

- tasks have clear file/component ownership,
- dependencies are explicit,
- agents are not racing to mutate the same artifact,
- the Orchestrator can reconcile outputs safely.

### Require independent QA when

- behavior changes,
- persistence/import logic changes,
- scoring/confidence behavior changes,
- a bug fix claims a regression is resolved,
- financial semantics change.

### Require security/data-integrity review when

- auth, authorization, tenant identity, secrets, tokens, migrations, real data, third-party tools, external network writes, financial reconciliation, or destructive behavior changes.

## Handoff format

Each handoff includes:

1. Outcome.
2. Scope/files.
3. Assumptions.
4. Verification performed.
5. Known limitations.
6. Risk/security implications.
7. Blockers.
8. Next owner/action.

## Context continuity

For a cold start, read:

1. `.github/copilot-instructions.md`
2. `AGENTS.md`
3. `PROJECT_BRIEF.md`
4. active issue/PR
5. relevant skill/module docs

Before ending substantial work, update `PROJECT_BRIEF.md` only if the durable project state materially changed.

## Anti-patterns

Avoid:
- five agents all editing the same feature,
- process ceremony for tiny changes,
- agents approving their own work,
- claiming tests/reviews happened without evidence,
- passing ambiguous money/security questions downstream as assumptions,
- adding agents because they look impressive rather than because a repeated workload needs a specialist.
