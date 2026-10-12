# Ledger — Product Quality Gate

Status: PROTOTYPE / NOT READY FOR CLIENTS

## Product goal
Build a reliable profit intelligence platform for small printing companies. Explain true profitability and evidence-backed opportunities to reduce avoidable costs. Do not pitch or onboard paying clients until quality gates are met.

## Non-negotiables
- No fabricated profit, savings, or causal claims.
- Every insight must show its source inputs, formula, period, and assumptions.
- Revenue is not profit. Do not infer expenses from sales-only records.
- Flag missing, duplicated, invalid, and incomplete records.
- Never imply a potential saving is guaranteed.
- Start with read-only imports and synthetic/anonymized test data.
- Avoid uploading sensitive client records to this public demo.

## Planned phases
1. Define data contracts: sales, expenses, job costs, refunds, and inventory (optional).
2. Implement deterministic calculation engine separate from UI.
3. Add automated tests for profit/margin math, refunds, duplicates, missing data, dates, and malformed uploads.
4. Add job-level margin and cost trend analysis.
5. Add explainable profit-leak findings with evidence and uncertainty.
6. Test mobile UI, error states, exports, and deployment stability.
7. Pilot with authorized, sanitized real business records and reconcile against accounting totals.
8. Release only after all critical tests pass and results are verified.

## Release checklist
- [ ] Validated calculation formulas and reconciliation
- [ ] Robust imports and clear errors
- [ ] Automated tests passing
- [ ] Data privacy and access model reviewed
- [ ] Mobile and desktop verified
- [ ] Deployment and recovery verified
- [ ] Real-data pilot verified with owner
- [ ] No critical or high-severity issues

Do not mark as production-ready until the checklist is complete.
