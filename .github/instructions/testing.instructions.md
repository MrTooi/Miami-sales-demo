---
applyTo: "tests/**/*.py"
description: "Testing standards for LEDGER, Opportunity Radar, and the AI operating layer"
---

# Testing standards

- Test behavior and invariants, not implementation trivia.
- Prefer small, deterministic tests with no unnecessary network dependency.
- Bug fixes should reproduce the prior failure when practical.
- Include boundary, malformed-input, duplicate/replay, and conflict cases when relevant.
- Financial tests must challenge precision, refunds, incomplete expenses, movement-vs-revenue semantics, and reconciliation ambiguity where applicable.
- Opportunity Radar tests must challenge fixed weights, repeatability, confidence separation, contradictory evidence, and invalid score/evidence inputs.
- Security-sensitive behavior should include explicit denial/isolation cases, not only happy-path access.
- A passing test suite is evidence of tested behavior, not proof of production readiness, security, compliance, or source completeness.
- Keep fixtures fictional/anonymized. Never add real customer, bank, accounting, credential, or identifying data.
