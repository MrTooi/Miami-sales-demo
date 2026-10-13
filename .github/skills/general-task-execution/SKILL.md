---
name: general-task-execution
description: Universal execution protocol for unfamiliar, cross-functional, or multi-step tasks. Use to classify work, reduce uncertainty, choose tools, verify outcomes, recover from failures, and hand off safely.
---

# General Task Execution

Use this skill when a task is unfamiliar, cross-functional, ambiguous, or not fully covered by a specialist skill.

## Goal

Produce a correct, evidenced result with the smallest safe amount of process. Never use confidence, verbosity, or apparent fluency as a substitute for verification.

## 1. Define the outcome

Before acting, identify:

- requested outcome,
- observable definition of done,
- constraints and exclusions,
- source of truth,
- risk if wrong,
- whether human approval is required.

If the user already supplied these, do not ask them again.

## 2. Route the work

Choose the strongest owner:

- Orchestrator: scope, sequencing, routing, architecture decisions.
- Backend: domain logic, persistence, APIs, migrations, financial logic.
- Integrations: external providers, OAuth, sync, imports, reconciliation boundaries.
- Research & Product: customer/market evidence, competitors, requirements, product decisions.
- Frontend & UX: user flows, UI implementation, accessibility, manual UI checks.
- QA/Critic: independent behavioral verification and regression hunting.
- Security & Data Integrity: auth, privacy, secrets, tenant boundaries, destructive/data-risk work.
- Generalist: unfamiliar tasks, operations, automation, data work, documentation, incident support.

Use multiple agents only when their independence or specialization adds value.

## 3. Build context before output

Inspect relevant files, issue/PR context, existing tests, project instructions, and available tools. For external technology, prefer current authoritative documentation. Do not invent APIs, file contents, account state, command results, market evidence, or tool capabilities.

## 4. Plan the smallest testable unit

Break large work into reversible increments. Each increment should have:

- a concrete deliverable,
- a check or test,
- a rollback/recovery path when practical,
- clear dependencies.

Avoid large speculative rewrites.

## 5. Execute

Use existing project patterns before creating new abstractions. Keep changes scoped. Preserve unknown work. Use least privilege for external tools.

## 6. Verify

Use the strongest available evidence appropriate to the task:

1. deterministic automated tests,
2. direct program output or API result,
3. focused manual verification,
4. authoritative source comparison,
5. independent reviewer/critic,
6. reasoned inference only when stronger evidence is unavailable.

Never report a check as passed unless it actually ran and passed.

## 7. Critique

Before handoff, ask:

- Did we satisfy every acceptance criterion?
- What could silently fail?
- Did we fabricate or assume anything?
- Did scope expand?
- Could this affect money, security, privacy, permissions, or customer trust?
- Is there a simpler design?
- Is a specialist or independent reviewer still needed?

## 8. Recover from failure

When a tool, test, or approach fails:

- inspect the actual error,
- identify whether the failure is deterministic, environmental, permission-related, or conceptual,
- change one meaningful variable at a time,
- do not retry the same failing action indefinitely,
- record unresolved blockers accurately.

## 9. Unknown-domain protocol

If the domain is unfamiliar:

1. identify exactly what is unknown,
2. search project context and authoritative documentation,
3. discover relevant skills/tools/plugins rather than pretending a capability exists,
4. run a small safe experiment,
5. compare the result against the definition of done,
6. escalate only if a materially risky ambiguity remains.

## 10. Handoff

Report:

- outcome,
- files/systems affected,
- evidence/tests,
- assumptions,
- remaining uncertainty,
- risk/security implications,
- next recommended owner/action.

## Hard stops

Require human approval before production deployment, destructive operations, secret/credential changes, live financial connections, external publication, purchases, permission expansion, or high-risk merges.
