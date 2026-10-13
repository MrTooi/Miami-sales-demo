---
name: agent-evaluation
description: 'Evaluation-driven protocol for benchmarking agent routing, instruction following, tool choice, correctness, escalation, security, and regression behavior before granting broader autonomy.'
---

# Agent Evaluation

Use this skill whenever the AI team, an individual agent, a new skill, or an autonomy rule is being evaluated or changed.

## Principle

Do not improve agents by intuition alone. Maintain a fixed benchmark, record failures, change one meaningful thing at a time, and rerun the benchmark.

## Evaluation layers

1. **Structural checks**
   - Agent profile/skill files exist and parse correctly.
   - Required roles and safeguards are present.
   - High-risk tasks have independent review and human-approval gates.

2. **Routing checks**
   - The Orchestrator chooses an owner capable of the task.
   - Cross-cutting work has one primary owner.
   - Specialized work reaches the specialist instead of a generic agent when risk justifies it.

3. **Behavioral checks**
   Evaluate whether the agent:
   - follows repository instructions,
   - uses the correct tools,
   - passes correct arguments,
   - handles missing tools honestly,
   - preserves scope,
   - tests/validates its work,
   - reports uncertainty,
   - escalates high-risk actions.

4. **Adversarial checks**
   Include:
   - prompt/tool injection,
   - malicious/untrusted evidence,
   - requests to skip tests,
   - requests to expose secrets,
   - destructive operations,
   - ambiguous financial semantics,
   - cross-tenant access,
   - pressure to claim completion without evidence.

5. **Regression checks**
   Every material agent failure should become a persistent benchmark case or explicit rule so the same failure is less likely to return.

## Scoring dimensions

For behavioral evals, score independently:

- task understanding,
- routing/ownership,
- instruction following,
- tool selection,
- factual/technical correctness,
- verification quality,
- security/data integrity,
- uncertainty handling,
- handoff quality.

Do not hide a security failure inside a high average score. Critical guardrail failures are blockers.

## Evaluator independence

Self-critique is useful but not sufficient. Quality-critical work should be challenged by QA/Critic, Security when relevant, deterministic tests, or a separate evaluator/run.

## Benchmark hygiene

- Keep benchmark cases stable enough to compare versions.
- Add new cases from real failures.
- Do not rewrite the benchmark merely because an agent failed it.
- Keep expected outcomes/rules separate from agent prompts.
- Record baseline and post-change results.
- Distinguish static capability coverage from real model-behavior evaluation.

## Autonomy gate

Before granting or expanding background autonomy, require:

- structural benchmark passing,
- no unresolved critical guardrail failure,
- representative behavioral evals once a runnable agent runtime is available,
- rollback/disable path,
- human approval boundaries documented,
- monitoring/audit trail sufficient to reconstruct what happened.

## Important limitation

A static benchmark proves role/rule coverage, not that a model will always behave correctly. Do not call agents fully trained, universally capable, or safe for unrestricted autonomy from configuration tests alone.