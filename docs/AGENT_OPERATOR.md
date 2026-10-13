# LEDGER AI Team Operator

## Goal

Create a provider-neutral operating layer that can keep making safe progress on queued repository tasks when Alex is not in ChatGPT.

The operator is not a single model. It is the control plane around the models: task queue, routing, risk classification, execution boundaries, review requirements, evidence, and human approval gates.

## Why this is separate from Claude or OpenAI

LEDGER must not stop because one model hits a usage limit. GitHub is the durable source of truth. Model providers are executors that can be plugged into the same task contract.

The intended path is:

`GitHub task queue -> deterministic operator -> selected executor -> isolated branch -> tests -> independent review -> human gate when required -> draft PR`

Claude remains on-demand. Connecting Claude Code does not make Claude the permanent executor.

## Phase 1: read-only planner

`.github/workflows/agent-operator.yml` is a read-only scheduled/manual planner.

It can:

- find open GitHub issues labeled `agent:ready`,
- ignore pull requests, paused tasks, claimed tasks, and tasks waiting on a human,
- select the next task deterministically by priority and issue number,
- route the task to the strongest configured specialist,
- classify risk,
- assign QA review to every queued task,
- add Security & Data Integrity review when the task touches integrations, financial data, auth/security, or higher risk,
- mark high-impact external actions as human-gated in its plan,
- emit a structured dispatch plan.

It cannot mutate issues, invoke a model, edit code, create a branch, open a PR, merge, deploy, or perform an external action.

The planner is scheduled twice per hour but remains disabled unless:

`LEDGER_AGENT_OPERATOR_ENABLED=true`

Manual dispatch is available for read-only testing.

## Phase 2: autonomous executor

`.github/workflows/agent-executor.yml` is the controlled execution worker.

It is scheduled once per hour but remains disabled unless:

`LEDGER_AGENT_EXECUTOR_ENABLED=true`

It also refuses to claim a task unless the repository has a protected GitHub Actions secret named:

`OPENAI_API_KEY`

The executor uses the official OpenAI Codex GitHub Action pinned to a specific commit. The action runs with the workspace permission profile. Repository dependencies are installed before the model step so the model does not need general network access for normal implementation work.

### Executor lifecycle

For one queued task per run:

1. Verify the OpenAI secret exists before touching the queue.
2. Run the operator safety tests.
3. Find the highest-priority eligible `agent:ready` issue.
4. Re-fetch it immediately before claim.
5. Divert human-gated work to `needs:human` before any model call.
6. Move safe work to `agent:claimed`.
7. Create a unique `agent/issue-<number>-<run>` branch.
8. Move the issue to `agent:working`.
9. Run the specialist implementation agent.
10. Enforce the autonomous scope guard.
11. Run the full repository test suite.
12. If no repository change exists, stop at `agent:blocked` without a PR.
13. Commit and push only the verified branch.
14. Open a **draft** pull request.
15. Run a separate QA / Critic model pass over the actual diff.
16. Run a separate Security & Data Integrity model pass when routing requires it.
17. Require structured reviewer verdicts.
18. If every required reviewer passes, move the issue to `agent:awaiting-review`.
19. If a safety check, test, publication step, or reviewer fails, stop at `agent:blocked` and preserve any already-published draft PR for diagnosis.

The executor does not auto-merge during the initial rollout.

## Queue contract

A task enters the queue only when an open issue has:

- `agent:ready`

Only a repository collaborator with issue-write access should apply this label. The label is the human authorization boundary for an issue to enter unattended execution.

Optional priority:

- `priority:p0`
- `priority:p1`
- `priority:p2`
- `priority:p3`

Optional explicit owner:

- `owner:backend`
- `owner:integrations`
- `owner:research`
- `owner:frontend`
- `owner:generalist`
- `owner:security`

Or area labels for deterministic routing, including:

- `area:backend`
- `area:persistence`
- `area:api`
- `area:integrations`
- `area:payments`
- `area:settlement`
- `area:reconciliation`
- `area:research`
- `area:product`
- `area:frontend`
- `area:ux`
- `area:security`

The operator will not dispatch issues carrying `agent:paused`, `agent:claimed`, `agent:working`, `agent:awaiting-review`, `agent:blocked`, or `needs:human` because those lifecycle states replace `agent:ready`.

Unknown or conflicting ownership routes to the Generalist Operator for triage instead of guessing.

## Lifecycle states

The operator owns these mutually exclusive lifecycle labels:

- `agent:ready` — human-authorized queue entry.
- `agent:claimed` — one executor run took ownership.
- `agent:working` — model execution is underway.
- `agent:awaiting-review` — implementation, tests, scope guard, and required automated reviewer gates passed; draft PR exists.
- `agent:blocked` — execution stopped on a concrete failure or unresolved reviewer finding.
- `needs:human` — policy requires a human decision before model execution or continuation.

The executor workflow uses a repository-wide concurrency group so two scheduled runs cannot work the queue simultaneously. A claimed issue is also re-checked before mutation so stale queue reads fail closed.

## Risk and human gates

Explicit `risk:low`, `risk:medium`, or `risk:high` labels are supported.

The following high-impact labels are always treated as high risk and cannot be downgraded by `risk:low`:

- `action:deploy`
- `action:delete`
- `action:publish`
- `action:purchase`
- `data:credentials`
- `data:live-financial`
- `permission:expand`

These tasks are transitioned to `needs:human` before any model is invoked.

## Autonomous self-modification boundary

Unattended product agents may not modify the AI operating system that governs them.

The scope guard blocks changes to the agent operator package, agent profiles, reusable agent skills, agent evaluation assets, core agent governance/tests, operator/executor workflows, and durable operating instructions such as `AGENTS.md`, `PROJECT_BRIEF.md`, and the operator/pipeline documentation.

Those files can still be changed through deliberate human-supervised branches and PRs such as this one.

The guard also rejects autonomous changes touching more than 30 files in one task. Large refactors must be decomposed or handled interactively.

## Review policy

Every autonomous implementation gets an independent QA / Critic pass after the implementation has passed tests and been committed to its isolated branch.

Tasks that touch integrations, payment settlement/reconciliation, financial data, auth/security, credentials, permissions, or medium/high risk also receive a Security & Data Integrity pass.

Reviewers return a structured verdict:

- `pass`
- `fail`
- `needs-human`

Every required reviewer must return `pass` for the issue to reach `agent:awaiting-review`. Malformed output, `fail`, or `needs-human` fails closed.

Claude is not used automatically. Claude Code remains available for deliberate high-value second-model review when usage is available.

## No automatic merge in initial rollout

The executor opens draft PRs only. It contains no automatic merge or deployment step.

This is intentional. The first rollout goal is autonomous **progress**, not irreversible autonomous authority. Once several real tasks have demonstrated correct claiming, execution, testing, review, and recovery behavior, low-risk auto-merge can be evaluated separately as a new permission increase.

## OpenAI credential and cost boundary

The official Codex GitHub Action requires an API credential supplied as a GitHub Actions secret. The secret must never be committed to the repository, issue text, comments, fixtures, screenshots, or logs.

Use a dedicated OpenAI project/key for the Ledger agent executor when possible so usage can be monitored and limited separately from other work.

Cost/rate controls in the first rollout are intentionally simple and auditable:

- executor disabled by default,
- only human-labeled `agent:ready` work is eligible,
- one task maximum per scheduled executor run,
- executor scheduled once per hour,
- 45-minute hard workflow timeout,
- implementation reasoning effort defaults to `medium`,
- review reasoning effort defaults to `medium`,
- Claude is never automatically triggered.

Optional repository variables:

- `LEDGER_CODEX_EFFORT`
- `LEDGER_CODEX_REVIEW_EFFORT`

If omitted, both default to `medium`.

## Activation checklist

Do not enable unattended execution until the branch containing this operator has been reviewed and merged.

Then:

1. Create a dedicated OpenAI API key/project for Ledger automation if desired.
2. Add the key to GitHub repository Actions secrets as `OPENAI_API_KEY`.
3. Keep `LEDGER_AGENT_EXECUTOR_ENABLED` unset/false.
4. Create a harmless synthetic issue and label it `agent:ready`.
5. Manually run **LEDGER AI Task Executor** once.
6. Verify claim, branch isolation, tests, draft PR creation, QA review, lifecycle state, and failure behavior.
7. Run a second synthetic test for a human-gated task and verify no model call occurs.
8. Only after both tests pass, set repository variable `LEDGER_AGENT_EXECUTOR_ENABLED=true`.
9. Queue real Opportunity Radar tasks deliberately with `agent:ready`.

## Claude usage policy

The existing Claude GitHub workflow remains on-demand only. The operator never automatically triggers Claude merely because a queued task exists. This lets Claude usage remain available for other work while Ledger continues through the OpenAI lane.

## Definition of done for the always-on system

The system is not considered autonomous merely because a scheduled workflow exists.

The milestone is complete only when controlled end-to-end trials prove that, while Alex is away, the system can:

1. discover an approved queued task,
2. claim it exactly once,
3. route it correctly,
4. execute only within allowed boundaries,
5. create isolated work,
6. run and report tests truthfully,
7. obtain the required independent review,
8. stop for a human gate when required,
9. preserve enough GitHub history to reconstruct what happened,
10. recover safely from failures,
11. move to the next safe queued task on a later run without needing an open chat session.
