# AI Operating Team

This repository uses a small, specialized AI team rather than one general agent doing everything.

## Why this exists

The goal is not to simulate an office for appearance. The goal is to let multiple agents work with clear ownership, independent review, durable project context, and human control over high-risk actions.

The team supports both current development and long-term company operations.

## Core team

### 1. Orchestrator

Purpose: coordinate work.

Owns:
- translating goals into scoped tasks,
- deciding sequencing and dependencies,
- writing acceptance criteria,
- assigning the correct specialist,
- deciding when QA/security review is required,
- maintaining `PROJECT_BRIEF.md`,
- summarizing readiness and blockers.

The Orchestrator normally does not write application code.

### 2. Backend Engineer

Purpose: build and maintain core product logic.

Owns:
- Opportunity Radar models and scoring,
- evidence persistence/ingestion,
- LEDGER financial logic,
- database models and migrations,
- service/API layers,
- deterministic calculations,
- tests for owned behavior.

### 3. Integrations Engineer

Purpose: safely connect external systems.

Owns:
- QuickBooks, Square, Plaid/banking, Xero and future provider work,
- OAuth/token lifecycle design,
- source schemas and normalization,
- retries, pagination and rate limits,
- idempotent sync behavior,
- webhook/import verification,
- provider-specific reconciliation boundaries,
- CSV/XLSX fallback behavior.

### 4. QA / Critic

Purpose: independently challenge correctness.

Owns:
- acceptance testing,
- regression analysis,
- edge cases,
- failure-path testing,
- reproducing bugs,
- verifying fixes,
- reviewing whether tests actually prove the claim being made.

QA should prefer evidence over confidence. It should not approve its own implementation work.

### 5. Security & Data Integrity

Purpose: protect customer trust and constrain agent autonomy.

Owns review of:
- authentication/authorization,
- tenant isolation,
- secrets and token handling,
- financial-data exposure,
- audit trails,
- destructive changes,
- tool/MCP/plugin permissions,
- prompt/tool injection boundaries,
- external data transmission,
- provenance and integrity controls.

## Default workflow

```text
Alex / product goal
        |
        v
   Orchestrator
        |
        +--> Backend Engineer
        |       |
        +--> Integrations Engineer (when relevant)
                |
                v
           self-review
                |
                v
           QA / Critic
                |
                +--> Security & Data Integrity (risk-based)
                |
                v
              CI
                |
                v
        human review / approval
                |
                v
              merge
```

Agents can work in parallel only when their files/dependencies do not conflict or the Orchestrator explicitly coordinates the overlap.

## Risk tiers

### Low risk

Examples: documentation, comments, isolated non-behavioral cleanup.

Required: focused review/checks.

### Normal risk

Examples: ordinary feature code, new Opportunity Radar data views, isolated persistence behavior.

Required: implementation tests + QA/critic review + CI.

### High risk

Examples:
- financial calculations,
- authentication/authorization,
- tenant isolation,
- migrations affecting customer data,
- real financial integrations,
- secrets/token handling,
- destructive actions,
- agent permission expansion,
- production deployment.

Required: implementation tests + independent QA + security/data-integrity review + CI + explicit human approval.

## Long-term role in the company

The AI team is intended to remain part of operations after initial product development.

Potential future agents may cover:
- customer insight/support triage,
- usage-pattern analysis,
- market/competitor monitoring,
- product analytics,
- documentation,
- release operations,
- growth research.

New agents should be added only after a repeated workload justifies specialization.

## Partner / Gemini boundary

The partner/Gemini workstream is the external validation function.

They own:
- customer research,
- interviews,
- competitors,
- willingness-to-pay evidence,
- GTM channels,
- pricing research,
- pilot recruitment.

Their findings should be imported into Opportunity Radar with provenance. They should not duplicate production engineering unless explicitly coordinated.

## Agent upgrade policy

Third-party agents, skills, MCP servers, plugins, and scripts are dependencies.

Before installation:

1. Confirm the source and maintainer.
2. Read what tools/permissions it requests.
3. Determine whether it sends data outside the environment.
4. Prefer a smaller local skill when equivalent.
5. Pin versions where practical.
6. Avoid giving financial/customer data to unreviewed tools.
7. Require human approval before enabling a tool with production credentials, destructive write access, or broad external transmission.

The project may use trusted public resources as patterns, including GitHub's `awesome-copilot`, but adapts them to repository-specific controls.

## Current team activation

Profiles live in `.github/agents/` and reusable workflows in `.github/skills/`.

Before substantial work, an agent should read:

1. `.github/copilot-instructions.md`
2. `AGENTS.md`
3. `PROJECT_BRIEF.md`
4. the active issue/PR
5. relevant domain skill(s)

At handoff, update durable context if a material decision, blocker, or next action changed.
