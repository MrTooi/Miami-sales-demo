# Agent Publication Recovery

## Purpose

Use publication recovery only when a LEDGER AI Task Executor run has already completed implementation and isolated verification, but publication or automated review stopped afterward.

Recovery exists to avoid repeating a paid implementation model call for work that is already frozen and verified.

It is **not** a general retry button and it does not make a failed implementation or verification acceptable.

## Workflow

`.github/workflows/agent-publication-recovery.yml` is manual-only.

Required inputs:

- `source_run_id`: the original `LEDGER AI Task Executor` run ID that produced the frozen artifacts.
- `issue_number`: the issue claimed by that run.

The workflow must be dispatched from protected `main`.

## Safety contract

Before doing any publication work, recovery:

1. freezes its recovery guard, scope guard, review gate, and review schema from the exact protected-main commit that launched the workflow;
2. verifies the source run belongs to this repository and was produced by `.github/workflows/agent-executor.yml`;
3. requires evidence that the source run completed both `implement-task` and `verify-task` successfully;
4. requires exactly one unexpired `ledger-task-contract` artifact and one unexpired `ledger-implementation-tree` artifact;
5. checks that the requested issue and deterministic branch name match the frozen task contract;
6. refuses to proceed when `needs:human` or `agent:paused` is present, or when the issue has not been explicitly restored to `agent:working`;
7. reconstructs the expected proposal from the frozen artifacts and re-validates it with the current protected-main scope guard.

## Existing branch behavior

If the reserved proposal branch does not exist, recovery may create and push it once after reconstructing and re-checking the exact manifest.

If the branch already exists, recovery does not overwrite it. It requires:

- exactly one proposal commit above the frozen base SHA;
- that commit's parent to equal the frozen base SHA;
- the branch tree to reconstruct to exactly the same verified manifest.

A mismatch fails closed. Recovery never force-pushes the proposal branch.

## Existing PR behavior

Recovery searches for an open PR from the reserved proposal branch to `main`.

- No matching PR: create one as a draft.
- Exactly one matching draft PR: reuse it.
- More than one matching PR, or a non-draft matching PR: fail closed for human review.

## Reviewer recovery

Recovery can resume the independent QA / Critic review and, when the frozen plan requires it, the Security & Data Integrity review.

Both reviewers run read-only. Recovery re-checks the proposal manifest after each reviewer and evaluates reviewer JSON with the review gate frozen from the protected-main recovery commit.

Recovery never invokes the primary implementation model.

## Lifecycle behavior

A successful recovery moves the issue to `agent:awaiting-review` only after all required automated reviewer gates pass.

A reviewer rejection or recovery failure moves the issue to `agent:blocked`, unless a human stop (`needs:human` or `agent:paused`) already exists. Human stop signals always win.

## What recovery does not do

Recovery does not:

- merge a pull request;
- deploy or publish product changes;
- access live customer financial data;
- override branch protection;
- overwrite an existing proposal branch;
- turn on unattended scheduling;
- retry a failed implementation or failed verification;
- silently replace human review.

## Trial #25 lesson

Trial #25 exposed why this workflow is necessary. Its verified proposal branch was pushed successfully, but the repository initially disallowed GitHub Actions from creating pull requests. A direct GitHub job rerun then replayed upstream jobs and attempted to push a second commit to the same branch, producing a non-fast-forward rejection and an avoidable repeat implementation call.

The permanent rule is: **publication failure must be recovered from frozen verified evidence, not by blindly rerunning the implementation pipeline.**
