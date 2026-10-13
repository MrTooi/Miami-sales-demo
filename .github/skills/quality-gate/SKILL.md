---
name: quality-gate
description: Verify that a change has enough evidence to be called ready: acceptance criteria, meaningful tests, regression coverage, independent challenge, CI evidence, known limitations, and risk-appropriate review.
---

# Quality Gate

Use before calling meaningful work complete or ready to merge.

## 1. Trace the claim

State exactly what the change claims to accomplish.

Then identify what evidence would prove that claim.

Examples:
- "duplicate imports are idempotent" needs replay tests,
- "profit remains unavailable with incomplete expenses" needs incomplete-data tests,
- "tenant isolation" needs cross-tenant denial tests,
- "market ranking is deterministic" needs repeatability and fixed-weight tests.

Do not substitute code coverage for behavioral evidence.

## 2. Check acceptance criteria

For each acceptance criterion mark:
- PASS with evidence,
- FAIL with evidence,
- UNKNOWN if not tested/proven.

UNKNOWN is not PASS.

## 3. Test layers proportionately

Use the smallest set that provides strong evidence:
- unit tests for pure logic,
- persistence/integration tests for storage and source boundaries,
- regression tests for bugs,
- end-to-end/browser checks for critical user flows when applicable,
- manual/exploratory checks where automation does not prove the behavior.

## 4. Adversarial review

Ask:
- What malformed input breaks this?
- What can be replayed twice?
- What happens on partial failure?
- What happens with stale/conflicting records?
- Does it cross tenant/source boundaries?
- Does it silently convert uncertainty into certainty?
- Can money be double-counted or rounded incorrectly?
- Does an error leak secrets/customer data?

## 5. Risk-specific gates

### Financial logic
Use the `financial-integrity` skill and independent QA.

### Market scoring/evidence
Use the `opportunity-validation` skill and verify provenance/confidence behavior.

### Auth, secrets, integrations, migrations, external agents/tools
Require Security & Data Integrity review.

## 6. CI evidence

Do not say CI passed until the relevant workflow completed successfully.

Record:
- workflow/run if available,
- tests/checks executed,
- pass/fail result.

## 7. Final readiness statement

Use one of:
- **Ready** — required checks passed; no known material blocker.
- **Ready with minor follow-ups** — core behavior proven; non-blocking items explicitly listed.
- **Blocked** — at least one material failure/unknown remains.

Passing tests do not by themselves mean production-ready, secure, compliant, or audited.
