# LEDGER Multi-Model AI Engineering Pipeline

## Purpose

This document defines how LEDGER uses multiple AI coding/reasoning systems without making any one provider the source of truth.

The authority order is:

1. Human product intent and explicit approvals
2. Repository instructions and issue acceptance criteria
3. Automated tests, CI, and agent evaluations
4. Independent model review
5. Individual model output

No model may approve its own high-risk work as final.

## Operating model

GitHub is the shared source of truth. Models do not need to share a chat. They coordinate through issues, branches, pull requests, review comments, tests, evaluation artifacts, and durable repository instructions.

The default workflow is:

`Human goal -> Orchestrator -> scoped GitHub issue -> primary model/agent -> branch -> tests -> independent model review -> QA/Security review -> CI/evals -> human approval -> merge`

## Provider-neutral routing

Agent roles remain defined in `AGENTS.md`. A role is not permanently tied to a model provider.

For each task the Orchestrator chooses:

- primary role,
- primary execution model,
- independent reviewer model,
- required repository reviewers,
- risk class,
- required tests/evals,
- approval gate.

Example routing metadata:

```text
Primary role: Backend Engineer
Primary model: codex
Independent model reviewer: claude-code
Required reviewers: QA/Critic, Security & Data Integrity
Risk: high
Human merge approval: required
```

A later task may reverse the models:

```text
Primary model: claude-code
Independent model reviewer: codex
```

The system should optimize for evidence and task fit rather than loyalty to a vendor.

## Initial model responsibilities

### OpenAI / ChatGPT / Codex

Best initial uses:

- product and architecture planning,
- issue decomposition,
- agent/evaluation design,
- scoped coding tasks,
- automated testing and debugging,
- independent review of Claude-authored changes,
- repository and evidence synthesis.

### Claude Code

Best initial uses:

- difficult implementation work,
- codebase-wide analysis,
- refactors with broad dependency awareness,
- independent review of Codex-authored changes,
- alternative architecture critiques,
- long-running repository tasks where Claude Code is a good fit.

These are routing defaults only. Actual performance in LEDGER evaluations should determine future routing.

## Branch and PR policy

- No AI agent writes directly to `main` for meaningful changes.
- Each implementation task uses a scoped branch.
- High-risk changes require independent model review before human merge approval.
- The model that authors a high-risk change should not be the only model that reviews it.
- A green badge is not sufficient if required tests were skipped.
- Review comments must distinguish verified defects from suggestions or uncertainty.

Recommended branch prefixes:

- `codex/`
- `claude/`
- `agent/`
- `eval/`
- `infra/`

## Permission boundaries

Models may normally:

- read repository content,
- work on scoped branches,
- create or update tests,
- open pull requests,
- post review comments,
- inspect CI,
- create synthetic evaluation artifacts,
- update documentation within assigned scope.

Human approval is required before:

- merging high-risk work,
- production deployment,
- destructive operations,
- live financial integrations,
- changing or expanding credentials/secrets,
- permission expansion,
- processing real customer financial data in unapproved systems,
- external publication or purchases.

Least privilege is the default.

## Handoff contract

Every model-to-model handoff must include:

- issue/task ID,
- requested outcome,
- branch/PR,
- files changed,
- assumptions,
- tests actually run and their results,
- unresolved failures,
- known uncertainty,
- financial/security/data implications,
- exact next reviewer/action.

The receiving model must inspect the actual diff and evidence rather than trusting the previous model's summary.

## Failure handling

If a model or tool fails:

1. Record the failure truthfully.
2. Do not invent a successful result.
3. Determine whether the failure is model reasoning, repository state, permissions, tool outage, CI infrastructure, or task ambiguity.
4. Retry only when retry is safe and idempotent.
5. Route to the alternate model when useful.
6. Add a regression/evaluation case when the failure represents a reusable weakness.

## Model evaluation

LEDGER should maintain model-specific performance evidence instead of assuming one model is universally strongest.

Track at minimum:

- task category,
- model used,
- first-pass test success,
- regressions introduced,
- independent-review findings,
- number of repair loops,
- token/cost usage when measurable,
- elapsed execution time when measurable,
- critical safety/data-integrity failures,
- human acceptance/rejection.

Routing policy can later use these results to choose the model with the strongest observed performance for each task type.

## First integration test

Before real product work resumes, run one synthetic multi-model handoff:

1. Create a harmless synthetic coding/debugging issue under the evaluation workbench.
2. Assign one model as primary implementer.
3. Require a scoped branch and tests.
4. Assign the other model as independent reviewer.
5. Require the reviewer to inspect the diff and test evidence.
6. Return valid findings to the primary model for repair.
7. Re-run tests/CI.
8. Record the complete handoff and result in GitHub.

Pass criteria:

- no product logic touched,
- no direct write to `main`,
- primary completes the scoped change,
- independent reviewer actually reviews the diff,
- test evidence is truthful,
- any valid review finding is repaired,
- no critical safety or data-integrity violation,
- handoff remains understandable without private chat history.

## Claude Code GitHub setup dependency

Claude Code's GitHub Action should be connected separately with least privilege. Until the Claude GitHub integration is installed and authenticated, Claude-specific tasks remain pending rather than being silently simulated by another model.

Once connected, the first test should be synthetic only. Do not authorize Claude Code to resume paused LEDGER or Opportunity Radar product issues merely because the integration exists.

## Current release posture

This pipeline setup does not authorize product implementation. Existing AI-team readiness gates remain in force. The purpose of this layer is to make future engineering work multi-model, auditable, and safer.