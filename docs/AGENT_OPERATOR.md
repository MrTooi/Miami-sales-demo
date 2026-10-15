# LEDGER AI Team Operator

## Goal

Create a provider-neutral operating layer that can make safe progress on explicitly approved repository tasks without requiring an open ChatGPT conversation.

The operator is the control plane around the models: task queue, routing, risk classification, immutable task contracts, execution boundaries, isolated verification, review evidence, lifecycle recovery, and human approval gates.

GitHub is the durable source of truth. OpenAI, Claude, or another model may act as an executor or reviewer, but no individual model is the authority for its own high-risk work.

## Current rollout status

Unattended execution is **disabled**.

Do not set either of these repository variables to true until the readiness gate in Issue #35 is complete and a human explicitly authorizes unattended scheduling:

- `LEDGER_AGENT_OPERATOR_ENABLED`
- `LEDGER_AGENT_EXECUTOR_ENABLED`

Manual workflow dispatch remains available for controlled synthetic trials.

Claude remains on-demand only and is never automatically invoked by Agent OS.

## Read-only planner

`.github/workflows/agent-operator.yml` is a read-only scheduled/manual planner.

It can:

- find eligible `agent:ready` issues,
- ignore paused, claimed, blocked, review-waiting, or human-gated work,
- select deterministically by priority and issue number,
- route to the configured specialist,
- classify risk,
- identify required reviewers,
- describe human gates.

It cannot mutate issues, invoke a model, edit code, open a PR, merge, deploy, or perform external actions.

The planner is scheduled twice per hour but only runs scheduled work when `LEDGER_AGENT_OPERATOR_ENABLED=true`.

## Controlled executor

`.github/workflows/agent-executor.yml` is the execution pipeline. It is scheduled once per hour but only runs scheduled work when `LEDGER_AGENT_EXECUTOR_ENABLED=true`. Manual dispatch is allowed for controlled tests.

It refuses to claim work unless the GitHub Actions secret `OPENAI_API_KEY` exists.

The executor uses the official OpenAI Codex GitHub Action pinned to a specific commit. Implementation and review are deliberately separated from publication authority.

## Trust-separated execution pipeline

One executor run handles at most one queued task.

### Job 1 — claim and freeze the task

The claim job has repository read permission and issue-write permission, but no repository contents-write permission.

It:

1. checks that the OpenAI credential is configured before taking ownership,
2. runs Agent OS safety tests,
3. checks out `main` explicitly and records the exact 40-character base commit SHA,
4. finds and re-fetches the next eligible `agent:ready` issue,
5. refuses autonomous pickup for an untrusted issue author,
6. applies human gates before any model call,
7. requires a machine-readable `## Allowed files` section with exact backtick repository paths,
8. rejects globs, parent-directory escapes, `.git` paths, and missing file boundaries,
9. claims the issue,
10. re-fetches the issue and stops if its title/body changed during claim,
11. freezes the issue contract, routing plan, exact allowed paths, and contract fingerprint into an immutable workflow artifact,
12. marks the issue `agent:working` only after that artifact exists.

For the initial rollout, autonomous tasks without an exact file allowlist fail closed to `needs:human`.

## Job 2 — implementation without publication authority

The implementation job has `contents: read` repository permission. It does **not** have repository contents-write or issue-write permission.

It:

1. checks out the exact claimed base SHA without persisted Git credentials,
2. downloads and verifies the frozen task artifact,
3. runs the implementation model with the workspace permission profile,
4. gives the model the exact allowed-path list in its prompt,
5. captures the resulting repository filesystem into an artifact while excluding `.git` metadata.

The implementation job cannot publish a branch or PR.

Its `.git` index, config, hooks, rename detection, ignore rules, or commits are never trusted as evidence of what changed.

## Job 3 — isolated verification with no write token or API secret

A fresh runner verifies the raw implementation artifact.

The verification job has repository read permission only and receives no OpenAI API secret.

It:

1. checks out the exact claimed base SHA,
2. reconstructs a trusted base tree,
3. extracts the implementation artifact into a separate model tree,
4. compares raw filesystem state rather than model-controlled git metadata,
5. enforces the frozen per-task file allowlist,
6. rejects protected control-plane/high-trust files,
7. rejects autonomous deletions,
8. rejects edits to existing tests,
9. permits new tests only when they are explicitly allowlisted `tests/test_*.py` files,
10. rejects symlinks, special files, and newly-added executable bits,
11. ignores only newly-created generated Python cache artifacts because those artifacts are never materialized into the proposal,
12. produces a deterministic change manifest,
13. materializes only verified regular files into a clean base checkout,
14. confirms the reconstruction exactly matches the manifest,
15. runs the full repository test suite,
16. re-checks the filesystem afterward and fails if tests changed the publishable proposal.

A proposal with no verified repository change fails instead of opening an empty PR.

## Job 4 — clean publication and read-only reviews

Only after isolated verification succeeds does a fresh publication job receive repository contents-write permission.

It independently repeats the scope check from the raw implementation artifact and frozen task contract, then:

1. creates the reserved task branch from the exact base SHA,
2. materializes only the verified manifest files into that clean checkout,
3. re-confirms the proposal matches the verified manifest,
4. commits and pushes from the clean checkout with git hooks disabled,
5. opens a **draft** pull request,
6. runs QA / Critic in `:read-only` mode,
7. runs Security & Data Integrity in `:read-only` mode when required,
8. verifies the repository proposal remained unchanged after each reviewer,
9. evaluates structured reviewer output using trusted base code,
10. moves the issue to `agent:awaiting-review` only if every required review gate passes.

The workflow contains no automatic merge or deployment path.

## Separate fail-safe recovery job

If implementation, verification, publication, or review fails, a separate fresh runner attempts to recover the lifecycle to `agent:blocked` without checking out or executing repository code.

It uses GitHub issue commands directly and does not trust model-modifiable Python for recovery.

A stale-claim reaper for hard workflow cancellation/runner loss remains part of the readiness gate before unattended scheduling is enabled.

## Queue contract

A task enters the queue only when an open issue has `agent:ready` and is otherwise eligible.

During the initial rollout, the issue must also:

- be authored by a trusted repository association (`OWNER`, `MEMBER`, or `COLLABORATOR`),
- contain `## Allowed files`,
- list the exact repository files the agent may change using backticks,
- avoid globs or implicit repository-wide scopes.

Example:

```markdown
## Allowed files

Create only:
- `agent_workbench/example.py`
- `tests/test_agent_workbench_example.py`
```

The frozen task artifact is the contract used by downstream verification and reviewers. Editing the GitHub issue after claim does not silently change the active run.

## Priority and routing

Optional priority labels:

- `priority:p0`
- `priority:p1`
- `priority:p2`
- `priority:p3`

Optional explicit owners:

- `owner:backend`
- `owner:integrations`
- `owner:research`
- `owner:frontend`
- `owner:generalist`
- `owner:security`

Area labels can also route work deterministically.

Conflicting ownership routes to Generalist for triage rather than guessing.

## Risk policy

Explicit `risk:low`, `risk:medium`, or `risk:high` labels are supported.

Unclassified work defaults to **medium**, not low. `risk:low` must therefore be an explicit classification during the initial rollout.

The following labels are always high-risk human gates and cannot be downgraded by `risk:low`:

- `action:deploy`
- `action:delete`
- `action:publish`
- `action:purchase`
- `data:credentials`
- `data:live-financial`
- `permission:expand`

These tasks move to `needs:human` before model execution.

## Lifecycle labels

Agent OS lifecycle labels are mutually exclusive:

- `agent:ready`
- `agent:claimed`
- `agent:working`
- `agent:awaiting-review`
- `agent:blocked`
- `needs:human`

Lifecycle transitions add/remove only lifecycle labels. They do not replace the issue's complete label set, so human-added priority, routing, risk, and data-boundary labels are preserved.

The executor uses a repository-wide concurrency group to prevent overlapping queue workers.

## Autonomous self-modification boundary

Unattended product agents may not modify the control plane that governs them.

Protected areas include:

- `agent_operator/`
- `agent_evals/`
- `.github/`
- `AGENTS.md`
- Agent OS/pipeline documentation and governance tests
- repository/dependency configuration files
- high-trust financial, integrity, persistence, and Opportunity Radar scoring modules during the initial rollout.

Existing tests cannot be modified or deleted autonomously. New tests are permitted only when the frozen task contract explicitly lists them and their names match `tests/test_*.py`.

Large autonomous changes remain capped at 30 publishable files and should normally be much smaller because the exact task allowlist is authoritative.

Human-supervised branches and PRs may deliberately change these controls, as with Agent OS hardening work itself.

## Review policy

Every publishable autonomous implementation receives QA / Critic review after isolated verification.

Medium/high-risk work and work involving financial data, integrations, payments, reconciliation, auth/security, credentials, or permission boundaries also receives Security & Data Integrity review.

Reviewers operate read-only against the clean published proposal.

Allowed structured verdicts are:

- `pass`
- `fail`
- `needs-human`

A `pass` is rejected if the same review contains a `blocking` or `important` finding. Malformed output and unknown finding severities also fail closed.

Claude is not used automatically. Deliberate cross-model Claude review is reserved for high-value checkpoints and important control-plane/product decisions.

## Branch protection is still required

The workflow's internal controls do **not** replace GitHub repository protection.

Before unattended execution is enabled, `main` must be protected with at least:

- PR required before merge,
- at least one human approval,
- required unit-test/status checks,
- force-push and deletion protection,
- no Actions/app bypass of the protected branch,
- code-owner/review rules for Agent OS and other high-trust files where supported.

Until that human repository configuration is complete, unattended scheduling remains disabled.

## Credential and cost boundary

`OPENAI_API_KEY` is stored only as a GitHub Actions secret and must never appear in repository files, issue text, screenshots, fixtures, or logs.

The initial rollout stays cost-aware:

- executor disabled by default,
- one task per run,
- deterministic checks before expensive model calls where possible,
- implementation reasoning defaults to `medium`,
- reviews default to `medium`,
- no automatic Claude calls,
- failures are diagnosed before paid retries.

Optional variables:

- `LEDGER_CODEX_EFFORT`
- `LEDGER_CODEX_REVIEW_EFFORT`
- `LEDGER_CODEX_MODEL`
- `LEDGER_CODEX_REVIEW_MODEL`

## Failure learning

A later successful retry does not erase a meaningful failure.

Relevant failures should become durable repository knowledge through the smallest useful combination of:

- a regression test/eval,
- a deterministic guard,
- a documented lesson,
- routing/prompt improvements,
- an added human gate,
- a cost/retry rule.

Blind retries are not the learning mechanism.

## Activation checklist

Do not enable unattended scheduling until all of these are true:

1. Agent OS hardening changes are reviewed and merged.
2. `main` branch protection is enabled by a human.
3. `LEDGER_AGENT_EXECUTOR_ENABLED` remains false/unset during trials.
4. Trial #25 passes end-to-end through clean-room verification and required reviews.
5. Trial #26 proves tenant isolation.
6. Trial #27 proves integration idempotency/conflict handling.
7. Trial #28 proves unfamiliar generalist transformation behavior.
8. The #29 human-gate behavior is re-confirmed if control-plane changes could affect it.
9. Scope-bypass, prompt-injection, review-gate, and failure-recovery evals pass.
10. Stale claim/cancellation recovery is demonstrated.
11. A final readiness review finds no Critical/High unattended-execution blocker.
12. A human explicitly authorizes enabling unattended scheduling.

Opportunity Radar and other product work can continue manually under normal branch/PR review, but unattended agents must not work on sensitive product logic until this readiness gate is complete.

## Definition of done

The system is not considered autonomous merely because a schedule exists.

It is ready only when controlled trials prove that it can:

1. discover only explicitly approved work,
2. freeze the exact task contract,
3. claim exactly once,
4. route and classify risk correctly,
5. execute without publication authority,
6. enforce exact file scope outside model-controlled git state,
7. run tests in a separate no-write-token environment,
8. publish only a clean reconstructed proposal,
9. obtain read-only independent review,
10. stop for human gates,
11. preserve enough evidence to reconstruct failures and decisions,
12. recover lifecycle state safely,
13. leave merge/deploy authority with humans until separately approved.
