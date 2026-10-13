# LEDGER Multi-Model AI Engineering Pipeline

## Purpose

LEDGER uses GitHub as the shared source of truth for OpenAI/ChatGPT/Codex, Claude Code, human approvals, tests, and audit history.

The goal is not to make one model the permanent winner. The goal is to route each task to the strongest available model, require evidence, and use independent review where it adds value.

## Authority order

1. Human product intent and explicit approval
2. Repository instructions and issue acceptance criteria
3. Automated tests, CI, and evaluation evidence
4. Independent model review
5. Individual model output

No model may treat its own high-risk work as final approval.

## Default workflow

`Human goal -> scoped GitHub task -> primary model -> isolated branch -> tests/evidence -> independent review when useful -> human approval -> merge`

Models do not need to share a live chat. They coordinate through GitHub issues, branches, pull requests, comments, tests, and durable repository instructions.

## Model routing

Agent roles remain provider-neutral. A task may use OpenAI as implementer and Claude as reviewer, or the reverse.

Initial routing defaults:

- OpenAI/ChatGPT/Codex: planning, task decomposition, repository synthesis, implementation, tests, debugging, and independent review.
- Claude Code: difficult implementation, broad codebase analysis, refactors, alternative architecture critique, and independent review.

These are starting defaults only. Future routing should be based on observed LEDGER performance.

## Claude usage policy

Claude Code is connected to this repository through GitHub Actions in on-demand mode.

Claude runs only when `@claude` is explicitly invoked in an issue or pull request interaction. Automatic review of every pull request is intentionally disabled to conserve Claude usage.

Use Claude when the expected value of a second model is high, such as:

- architecture-sensitive changes,
- difficult debugging,
- security or data-integrity review,
- broad refactors,
- high-risk product logic,
- deliberate cross-model evaluation.

Routine low-risk work should not call Claude automatically.

## Branch and merge policy

- Meaningful AI work must not write directly to `main`.
- Use scoped branches and pull requests.
- High-risk changes require human approval before merge.
- A green check is not enough when required tests were skipped.
- Reviews must separate verified defects from suggestions and uncertainty.
- Production deployment, destructive actions, credential changes, and live financial integrations always require human approval.

## Handoff contract

A model-to-model handoff should include:

- issue/task ID,
- requested outcome,
- branch or PR,
- files changed,
- assumptions,
- tests actually run and results,
- unresolved failures,
- uncertainty,
- security/data implications,
- exact next reviewer or action.

The receiving model should inspect the actual diff and evidence rather than trusting the previous model's summary.

## Failure handling

If a model or tool fails:

1. Record the failure truthfully.
2. Do not invent a successful result.
3. Identify whether the cause is reasoning, repository state, permissions, tooling, CI, or ambiguity.
4. Retry only when safe and useful.
5. Route to the alternate model when appropriate.
6. Turn reusable failures into future regression or evaluation cases.

## Performance tracking

For meaningful model evaluations, track:

- task category,
- model used,
- first-pass success,
- regressions introduced,
- independent-review findings,
- repair loops,
- usage/cost when measurable,
- elapsed execution time when measurable,
- safety/data-integrity failures,
- human acceptance or rejection.

## First cross-model smoke test

The initial GitHub handoff test was completed on October 13, 2026 using an isolated synthetic PR.

OpenAI/GPT created a deliberately flawed evaluation helper and tests on a non-product branch. Claude Code was invoked exactly once as an independent reviewer through the on-demand GitHub Action.

Claude successfully inspected the diff and identified the concrete defect: the implementation used `set()` and therefore failed to preserve deterministic first-seen order, while the tests failed to assert ordering. Claude also explicitly reported its limitations and did not modify product code.

The synthetic PR was closed without merging into `main`.

This validated the core communication path:

`OpenAI/ChatGPT -> GitHub -> Claude Code -> GitHub review -> OpenAI/ChatGPT`

The test also confirmed that Claude can be invoked selectively rather than automatically, preserving usage for high-value tasks.

## Current state

- Claude Code GitHub App: connected to `MrTooi/Miami-sales-demo` only.
- Claude GitHub workflow: on-demand only.
- Automatic Claude PR review: disabled.
- Synthetic cross-model handoff: validated.
- Product implementation is not automatically authorized by this setup.
- Opportunity Radar and future AI agents should use this pipeline as the engineering coordination layer.