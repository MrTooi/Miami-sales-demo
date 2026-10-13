# LEDGER AI Team Operator

## Goal

Create a provider-neutral operating layer that can keep making safe progress on queued repository tasks when Alex is not in ChatGPT.

The operator is not a single model. It is the control plane around the models: task queue, routing, risk classification, execution boundaries, review requirements, evidence, and human approval gates.

## Why this is separate from Claude or OpenAI

LEDGER must not stop because one model hits a usage limit. GitHub is the durable source of truth. Model providers are executors that can be plugged into the same task contract.

The intended path is:

`GitHub task queue -> deterministic operator -> selected executor -> branch/PR -> tests -> independent review -> human gate when required`

Claude remains on-demand. Connecting Claude Code does not make Claude the permanent executor.

## Phase 1: safe planner foundation

The current implementation is deliberately read-only.

`agent_operator/` can:

- find open GitHub issues labeled `agent:ready`,
- ignore pull requests, paused tasks, claimed tasks, and tasks waiting on a human,
- select the next task deterministically by priority and issue number,
- route the task to the strongest configured specialist,
- classify basic risk,
- require QA review for every queued task,
- add Security & Data Integrity review when the task touches integrations, financial data, auth/security, or higher risk,
- mark high-impact external actions as human-gated,
- emit a structured dispatch plan.

It cannot yet:

- call OpenAI, Claude, Gemini, or another model,
- claim or mutate an issue,
- create an implementation branch,
- edit product code,
- open or merge a pull request,
- deploy, delete, publish, purchase, expand permissions, or access live financial/credential data.

This boundary is intentional. We verify routing and policy before attaching an autonomous executor.

## Queue contract

A task enters the queue only when an open issue has:

- `agent:ready`

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

The operator will not dispatch issues carrying `agent:paused`, `agent:claimed`, or `needs:human`.

Unknown or conflicting ownership routes to the Generalist Operator for triage instead of guessing.

## Risk and human gates

Explicit `risk:low`, `risk:medium`, or `risk:high` labels are supported.

The following high-impact labels are always treated as human-gated external actions:

- `action:deploy`
- `action:delete`
- `action:publish`
- `action:purchase`
- `data:credentials`
- `data:live-financial`
- `permission:expand`

Agents may still prepare analysis or branch-scoped work when safe, but the external action itself must remain blocked until a human approves it.

## Background workflow

`.github/workflows/agent-operator.yml` contains a scheduled planner that wakes twice per hour.

Scheduled operation is disabled by default. The job runs on schedule only when the repository variable below is explicitly set to `true`:

`LEDGER_AGENT_OPERATOR_ENABLED=true`

A human can also run the workflow manually through GitHub Actions while the repository variable is still disabled.

The Phase 1 workflow has read-only repository permissions and does not invoke a model.

## Executor phase

The next milestone is to add an executor adapter behind the planner.

Candidate executors include:

1. OpenAI Codex for the primary engineering lane.
2. Claude Code as an explicitly requested second model or alternate executor.
3. Future providers if evaluation evidence shows they improve a task category.

The executor must receive the same structured dispatch contract and must not bypass repository policy.

Before an executor is allowed to run unattended, it must prove:

- branch isolation,
- no direct writes to `main`,
- truthful test reporting,
- deterministic task claiming,
- no duplicate concurrent claims,
- time/token/run limits,
- safe retry behavior,
- review routing,
- stop conditions,
- human gates for high-impact actions,
- audit trail in GitHub.

## OpenAI automation note

Current OpenAI guidance supports Codex in GitHub Actions and CI, but automated GitHub Action use requires a protected execution credential/runtime. We will not place credentials in source or enable that executor until the authentication and spend boundary is deliberately approved.

## Claude usage policy

The existing Claude GitHub workflow remains on-demand only. The operator must never automatically trigger Claude merely because a queued task exists. A future Claude adapter must require an explicit provider decision or review policy so Roblox/game usage and Ledger usage do not compete unnecessarily.

## Definition of done for the always-on system

The system is not considered autonomous merely because a scheduled workflow exists.

The milestone is complete only when a controlled end-to-end trial proves that, while Alex is away, the system can:

1. discover an approved queued task,
2. claim it exactly once,
3. route it correctly,
4. execute only within allowed boundaries,
5. create isolated work,
6. run and report tests truthfully,
7. request independent review when required,
8. stop for a human gate when required,
9. preserve enough GitHub history to reconstruct what happened,
10. move to the next safe task without needing an open chat session.
