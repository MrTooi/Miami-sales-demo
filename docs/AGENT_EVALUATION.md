# AI Team Evaluation

## Purpose

Treat the AI team like software: define representative tasks, measure capability coverage, require independent review for high-risk work, preserve failures, and improve the configuration before trusting broader autonomy.

This document does **not** claim the team can complete every possible task. No prompt or agent profile can guarantee that. The goal is broad, reliable coverage with explicit routing, verification, and safe failure behavior.

## What is currently measured

The deterministic benchmark in `agent_evals/` contains 24 representative scenarios spanning:

- backend development,
- external integrations,
- financial correctness,
- authorization and tenant isolation,
- market/customer research,
- interview and competitor synthesis,
- frontend/UX and accessibility,
- migrations and API changes,
- performance and release readiness,
- agent/tool security,
- destructive-data requests,
- third-party agent evaluation,
- unfamiliar one-off tasks,
- automation/operations,
- incident triage,
- data analysis,
- architecture,
- documentation,
- product requirements,
- manual QA.

The benchmark measures two things:

1. **Capability coverage** — whether the team has at least one explicit owner for every capability required by the scenario.
2. **High-risk independent review** — whether high-risk work has separate QA and/or security/data-integrity coverage as appropriate.

Score formula:

- 80% capability coverage
- 20% high-risk independent-review coverage

## Evaluated lineups

### Original five

Orchestrator, Backend, Integrations, QA/Critic, Security & Data Integrity.

Preliminary deterministic result:

- Capability coverage: 54.2%
- High-risk review coverage: 100%
- Composite score: 63.33 / 100

Main gaps: market/customer research, product analysis, frontend/UX, accessibility, general automation/operations, incident ownership, data-analysis ownership, and unfamiliar-task fallback.

### Generic three-agent reference pattern

Producer, broad Dev, QA. This is included only as a simple external reference pattern, not as a claim about all GitHub Copilot configurations.

Preliminary deterministic result:

- Capability coverage: 16.7%
- High-risk review coverage: 0%
- Composite score: 13.33 / 100

This reference is intentionally generic and lacks repository-specific financial/security/product specialization.

### Expanded eight-agent candidate

Orchestrator, Backend, Integrations, Research & Product, Frontend & UX, Generalist, QA/Critic, Security & Data Integrity.

Preliminary deterministic result:

- Capability coverage: 100%
- High-risk review coverage: 100%
- Composite score: 100 / 100

This means the candidate lineup covers all **defined benchmark scenarios**. It does not prove perfect execution or universal intelligence.

## Why the team was expanded

Adding agents is justified only when a benchmark exposes a durable ownership gap. The added roles are:

- **Research & Product Analyst** for evidence, customer/market research, competitors, product requirements, and business decisions.
- **Frontend & UX Engineer** for user-facing implementation, flows, accessibility, and manual UI behavior.
- **Generalist Operator** for unfamiliar one-off tasks, automation, operations, data work, documentation, and incident support.

The Generalist is a fallback, not a replacement for specialists.

## Training approach

We are not fine-tuning model weights. "Training" in this repository means durable behavioral instruction and evaluation:

- role-specific agent profiles,
- repository-wide rules,
- task-specific skills,
- deterministic tests and hooks where possible,
- representative eval scenarios,
- failure-to-regression-test loops,
- runtime traces/behavioral evaluation when the target agent runtime is available.

The universal fallback protocol is `.github/skills/general-task-execution/SKILL.md`.

## Runtime evaluation still required

Static capability coverage is necessary but insufficient. It can verify that the organization has an owner and review path for a task class, but it cannot prove that an LLM will execute the task correctly.

Before resuming broad autonomous project work, run behavioral evaluations in the actual target runtime and score at least:

- routing accuracy,
- requirement completion,
- factual grounding,
- tool choice,
- test quality,
- error recovery,
- security/privacy behavior,
- scope discipline,
- uncertainty honesty,
- handoff quality.

Each meaningful runtime failure should become a durable regression scenario or deterministic safeguard when practical.

## Release criteria for the team

The AI team should not be called broadly ready until:

- configuration/benchmark tests pass,
- all critical task categories have explicit ownership,
- high-risk scenarios have independent review coverage,
- existing product tests remain green,
- runtime behavioral tests have been performed when agent execution access is available,
- no known critical safety or correctness benchmark failures remain.

## Important operational rule

Project Issue #1 remains paused while the team is under evaluation. Agent benchmarking and hardening must be completed before its execution authorization is restored.
