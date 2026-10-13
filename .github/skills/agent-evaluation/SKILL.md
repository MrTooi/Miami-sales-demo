---
name: agent-evaluation
description: Evaluate agent or team performance against task scenarios, acceptance criteria, safety gates, and evidence quality; record failures and convert them into durable improvements.
---

# Agent Evaluation

Use this skill before trusting new agents broadly and after material agent failures.

## Principles

- Evaluate behavior against explicit scenarios, not vibes.
- Separate capability coverage from actual execution quality.
- A passing structural/config test is not proof of good reasoning.
- High-risk tasks require independent review, not self-certification.
- Preserve failed examples; they are training data for better instructions and tests.

## Evaluation dimensions

Score or judge as applicable:

1. Correct task routing.
2. Requirement coverage.
3. Factual grounding and provenance.
4. Tool selection and least privilege.
5. Test/verification quality.
6. Error recovery.
7. Security/privacy/data-integrity behavior.
8. Scope discipline.
9. Honest uncertainty.
10. Handoff quality.

## Benchmark process

1. Define representative scenarios before tuning the agent.
2. Include ordinary, ambiguous, adversarial, failure, and high-risk cases.
3. Record expected owner, required capabilities, approvals, and success checks.
4. Run the same scenarios after instruction/skill changes.
5. Compare results; do not move the goalposts to make a preferred agent win.
6. Keep a regression scenario for every meaningful failure.

## Failure-to-improvement loop

For each failure, record:

- scenario,
- expected behavior,
- actual behavior,
- severity,
- root cause category,
- whether the problem belongs in an agent profile, reusable skill, deterministic test/hook, tool permission, or human process,
- remediation,
- regression test.

Prefer deterministic controls over more prompt text when a rule can be enforced mechanically.

## Release gate

Do not declare an agent/team broadly ready unless:

- its required configuration files validate,
- representative capability coverage meets the project threshold,
- high-risk scenarios have independent review coverage,
- the repository test suite remains green,
- known critical benchmark failures are resolved or explicitly accepted,
- behavioral runtime evaluation is completed when the target runtime is available.

## Important limitation

Static capability benchmarks tell us whether a team design has an owner and safeguards for a class of work. They do not prove the underlying model will execute every task correctly. Runtime traces and real task outcomes are still required for behavioral confidence.
