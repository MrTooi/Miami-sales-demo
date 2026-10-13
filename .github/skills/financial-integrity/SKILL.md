---
name: financial-integrity
description: Apply LEDGER's exact-money, provenance, completeness, deduplication, reconciliation, and auditability rules whenever financial records or calculations are changed or reviewed.
---

# Financial Integrity

Use this skill for any code, test, review, schema, import, or integration that can affect financial meaning.

## Exact money

- Use `Decimal` or an equivalent exact fixed-point representation.
- Reject non-finite values and unsupported precision rather than silently rounding unless a documented business rule explicitly requires rounding.
- Do not convert exact monetary values through binary floating point in core calculations.

## Revenue and movement

Do not double-count money movement.

Example:
- sale: $1,000
- fee: $30
- payout: $970
- bank deposit: $970

Revenue is not $1,970. Payout/deposit records are movement/evidence for reconciliation, not additional sales.

## Expense completeness

- Missing expenses are not zero expenses.
- Recorded expenses may be displayed as recorded amounts.
- Profit must remain unavailable/provisional when required expense coverage is not confirmed.
- Never fabricate costs or savings to make analysis feel complete.

## Identity and deduplication

- Preserve tenant/workspace + source + external record identity.
- Exact replay should be idempotent.
- Same external ID in a different source/tenant is not automatically a duplicate.
- Conflicting revisions should not silently overwrite canonical data.
- Preserve enough information to investigate conflicts.

## Reconciliation

- Matching amount alone is a suggestion, not proof, when multiple candidates exist.
- Ambiguous groups require review.
- Reconciliation must not cross tenants.
- A reconciled movement does not prove that the upstream source is complete or that a bank balance is correct.

## Provenance

Every important calculated result should be traceable to source records and transformation rules.

Preserve:
- source/provider,
- stable external ID,
- record type,
- timestamps where relevant,
- currency,
- canonical/import status,
- evidence needed for reconciliation or conflict review.

## Required test thinking

For relevant changes test:
- zero and boundary amounts,
- refunds/negative sales,
- more than two decimal places,
- duplicates and replay,
- conflicts,
- missing expenses,
- empty periods,
- fee/payout/deposit semantics,
- ambiguous reconciliation,
- tenant separation.

## Claims

Do not use words such as `verified`, `audited`, `complete`, `secure`, or `true profit` unless the implemented evidence supports that exact claim.
