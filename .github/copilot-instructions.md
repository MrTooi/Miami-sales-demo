# Repository-wide AI instructions

This repository contains two related systems:

- **LEDGER**: a prototype financial/profit-intelligence product for small businesses.
- **Opportunity Radar**: an internal evidence and market-validation system used to decide which customer/problem deserves deeper investment.

## Non-negotiable rules

1. Do not call any feature production-ready, secure, verified, compliant, or complete without evidence.
2. Never weaken financial validation, tenant isolation, duplicate protection, reconciliation safeguards, auditability, or tests for convenience.
3. Use `Decimal` for financial calculations. Never introduce floating-point money calculations into financial logic.
4. Do not invent financial data, market evidence, customer quotes, confidence, ROI, savings, or willingness-to-pay claims.
5. Separate observed evidence from inference and recommendation.
6. Opportunity Radar ranking math must remain deterministic and auditable. AI may summarize evidence but must not secretly alter scoring weights or scores.
7. Preserve source provenance for research evidence.
8. Public demos must use fictional or anonymized data only.
9. Never commit credentials, access tokens, API keys, customer secrets, confidential financial files, or real bank/accounting data.
10. New behavior requires tests. Bug fixes should add a regression test when practical.
11. Run the repository test suite before claiming a change passes.
12. Do not merge directly into `main`. Work on a branch and use a pull request for meaningful changes.
13. Keep changes narrow to the assigned task. Do not opportunistically rewrite unrelated code.
14. If a requirement is ambiguous and a wrong assumption could affect money, security, data integrity, or customer trust, stop and surface the ambiguity.
15. Human approval is required before production deployment, destructive changes, real financial integrations, or merging high-risk changes.

## Current strategic priority

The current priority is **proving what market/problem is worth building for**. UI polish is secondary to evidence quality, product value, reliability, and customer validation.

## Opportunity Radar evidence hierarchy

Prefer stronger evidence over weaker evidence:

1. Paid customer behavior
2. Pilot behavior
3. Signed commitment / deposit / LOI
4. Explicit willingness-to-pay evidence
5. Customer interviews with quantified pain
6. Existing spending or workarounds
7. Software reviews
8. Forums/community evidence
9. Industry reports
10. General speculation

A high opportunity score with weak evidence must still show low confidence.

## Engineering workflow

Use: roadmap/issue -> scoped branch -> implementation -> tests -> review -> CI -> human approval -> merge.

When reporting work, state:
- what changed,
- what tests were run,
- what remains uncertain,
- any security/data-integrity implications,
- and the next recommended step.
