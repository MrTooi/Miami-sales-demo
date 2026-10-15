# Agent Publication Recovery

## Purpose

Use publication recovery only when a LEDGER AI Task Executor run has already produced a frozen implementation artifact but publication or automated review stopped afterward.

Recovery exists to avoid repeating a paid implementation-model call for work that can be independently reconstructed and re-verified.

It is **not** a general retry button. It does not make a failed implementation acceptable, and it never skips fresh verification.

## Workflow

`.github/workflows/agent-publication-recovery.yml` is manual-only and must be dispatched from protected `main`.

Required inputs:

- `source_run_id`: the original `LEDGER AI Task Executor` run ID that produced the frozen artifacts.
- `issue_number`: the issue claimed by that run.

Recovery has two permission-separated stages:

1. **Read-only recovery verification** reconstructs the proposal from frozen source artifacts, re-runs scope verification, computes the exact expected Git tree, and runs the repository test suite. This job has no write permission and no implementation-model secret.
2. **Publication and review** receives only the verified identity outputs, reconstructs the proposal again, re-proves the exact Git tree, safely reuses or creates the draft PR, and runs independent read-only QA and Security/Data Integrity reviews.

The primary implementation model is never invoked by the recovery workflow.

## Trusted control plane

At the start of each recovery job, the workflow freezes these controls from the exact protected-main commit that launched the recovery:

- `agent_operator/recovery.py`
- `agent_operator/scope_guard.py`
- `agent_operator/review_gate.py`
- `agent_operator/review_schema.json`

Their SHA-256 hashes are recorded and re-checked before sensitive verification/review steps. The failed source run supplies task/proposal evidence, not the safety code that judges recovery.

## Source-run and contract evidence

Recovery verifies that the source run:

- belongs to this repository;
- is `.github/workflows/agent-executor.yml`;
- originated from `main`;
- is completed;
- used a supported executor trigger;
- completed an implementation job successfully;
- exposes exactly one unexpired `ledger-task-contract` artifact and one unexpired `ledger-implementation-tree` artifact.

New executor runs freeze recovery metadata alongside the task and prompt. The metadata binds:

- the actual checked-out base commit SHA;
- GitHub run ID;
- run attempt;
- SHA-256 of the frozen task contract;
- SHA-256 of the frozen implementation prompt.

The executor preserves that metadata inside the uploaded `ledger-task-contract` artifact.

Legacy runs created before this metadata existed may be recovered only through a strict fallback: the reserved proposal branch must already exist as exactly one commit directly above the source-run head. If that relationship cannot be proven, recovery fails closed.

## Independent recovery verification

Before a write-capable recovery job can start, the read-only verification job:

1. validates issue/branch identity and the recovered base;
2. refuses `needs:human` or `agent:paused` and requires explicit `agent:working` state;
3. reconstructs the frozen base tree and implementation tree;
4. re-runs the current protected-main scope guard;
5. materializes only the verified manifest into the clean base;
6. computes the exact expected Git tree with `git write-tree`;
7. runs the full repository unit-test command;
8. re-checks the publishable proposal after tests;
9. records a short-lived recovery-evidence artifact containing the source run, issue, branch, base SHA, exact expected tree, task/prompt hashes, and source artifact identifiers/digests.

Model-authored code therefore does not get write permission merely because an older executor verification once succeeded.

## Existing branch behavior

If the reserved proposal branch does not exist, recovery may create and push it once after rebuilding the exact proposal.

If the branch already exists, recovery never overwrites it. Reuse requires all of the following:

- exactly one proposal commit above the frozen base SHA;
- that commit's parent equals the frozen base SHA;
- the branch's **exact Git tree object ID** equals the independently reconstructed expected tree.

The exact-tree requirement is stronger than comparing only allowed-file manifests: extra tracked cache files, gitlinks, or any other tracked Git object change the tree identity and cause recovery to fail closed.

Recovery never force-pushes the proposal branch.

## Existing PR behavior

Recovery searches for an open PR from the reserved proposal branch to `main`.

A reusable PR must be:

- exactly one matching open PR;
- draft;
- same-repository, not cross-repository;
- owned by the repository owner;
- targeted at `main`;
- pinned to the exact proposal commit being reviewed.

If no matching open PR exists, recovery may create one draft PR only when there is no previously closed PR for that proposal branch. Ambiguous or previously closed-PR states fail closed for human review.

## Exact-commit reviewer binding

Before reviewers run, after each reviewer, and immediately before lifecycle promotion, recovery re-checks:

- the remote proposal branch SHA;
- the PR head SHA;
- the local exact Git tree where relevant;
- the frozen recovery-control hashes.

Reviewer comments include the exact commit SHA they reviewed.

The recovery path always runs both:

- independent QA / Critic review;
- independent Security & Data Integrity review.

Both reviewers use read-only model permissions. Recovery does not rely on the old task artifact to decide whether Security review is necessary.

## Lifecycle behavior

A successful recovery moves the issue to `agent:awaiting-review` only after:

- independent recovery verification succeeds;
- the exact branch/PR identity is proven;
- QA passes;
- Security/Data Integrity passes;
- the review gate passes;
- the exact reviewed commit is still unchanged;
- no human stop is active.

If a human stop arrives during lifecycle promotion, recovery removes its own `agent:awaiting-review` state and fails closed so the human state wins.

A reviewer rejection or recovery failure moves a validated issue to `agent:blocked`, unless `needs:human` or `agent:paused` already exists. The fail-safe job does not execute repository code and only acts on an issue number validated from the frozen contract.

## What recovery does not do

Recovery does not:

- invoke the primary implementation model;
- merge a pull request;
- deploy or publish product changes;
- access live customer financial data;
- override branch protection;
- force-push or overwrite a proposal branch;
- turn on unattended scheduling;
- convert a failed verification into a pass;
- silently replace human merge review.

## Trial #25 lesson

Trial #25 exposed why this workflow is necessary. Its verified proposal branch was pushed successfully, but the repository initially disallowed GitHub Actions from creating pull requests. A direct GitHub job rerun replayed upstream jobs, repeated an implementation call, and then attempted to push a second commit to the already-existing branch, producing a non-fast-forward rejection.

The permanent rule is:

**publication failure must be recovered from frozen evidence through fresh read-only verification, not by blindly rerunning the implementation pipeline.**
