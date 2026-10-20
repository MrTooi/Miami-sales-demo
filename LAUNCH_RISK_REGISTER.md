# LEDGER — Launch Risk Register and Mitigation Plan

**Status:** PROTOTYPE. This document is a plan, not evidence that controls are implemented or tested.

## Release rules
1. Never expose confidential client financial records through the public Streamlit demo.
2. Do not accept paying clients until critical financial, security, and operational controls are independently verified.
3. Mark each financial metric as verified, provisional, or unavailable. Never turn missing information into zero.
4. Keep the source, date range, formula, accounting basis, and last synchronization timestamp for each result.
5. Prefer approved APIs and exports; never request payment passwords, scrape private accounts, or bypass access restrictions.

## P0 — Must resolve before any real client data

| Risk | Required solution | Acceptance test |
|---|---|---|
| Tenant data leakage | Authenticated accounts, server-side tenant-scoped queries, row-level controls, least-privilege roles | User A cannot retrieve or modify User B's records via UI, URL, API, export, or background job |
| Sensitive uploads in public demo | Separate private production environment; restrict uploads; encryption in transit/at rest; retention and deletion policies | Public demo cannot store or reveal confidential business data |
| Incorrect revenue due to duplicate sources | Canonical transaction ledger with provider/source IDs; match payments, fees, payouts, bank deposits, and bookkeeping entries | Square $1,000 sale less $30 fee plus $970 deposit yields $1,000 gross sales, not $1,970 |
| Misleading profit | Require complete expense coverage, reporting-period checks, cost classification and accounting-basis confirmation | Sales-only or incomplete-expense import displays profit unavailable/provisional |
| Unauthorized integrations | Official OAuth or supported authorization; securely stored and rotated credentials; minimum scopes | Disconnect revokes access; no passwords stored; expired tokens handled |
| Financial import corruption | Preserve amount as string until Decimal; exact cents; strict schemas, rejected-row review, date and currency checks | $0.10 + $0.20 is exactly $0.30, malformed rows never silently disappear |
| Lost/changed records | Immutable source events and auditable corrections; idempotent upserts and deletion handling | Duplicate, revised, removed and reimported records reconcile correctly |

## P1 — Must resolve before commercial launch

| Risk | Required solution | Acceptance test |
|---|---|---|
| API outages / expired authorization | Sync status, exponential backoff, replay, reauthorization, alerts | Disconnect and recovery scenario ends with complete reconciled records |
| Webhook duplicates / out-of-order events | Signature validation, event IDs, idempotency, periodic full reconciliation | Replay events in random order without changing final balances |
| Pending vs posted bank transactions | Link pending and posted items; process additions, modifications and removals | Pending $100 becomes posted $98 without counting both |
| Refunds, disputes and chargebacks | Link adjustment to original payment, distinguish processing date from original sale date | Refund and fee treatment agrees with selected reporting basis |
| Partial date coverage | Track per-source coverage windows and time zones; missing periods flagged | Missing one week of expenses prevents verified monthly profit |
| Multi-currency / tax / tips | Store original currency, taxes, tips and exchange-rate provenance; avoid mixing currencies | Mixed USD/CAD never silently summed |
| Unrecorded cash | POS/accounting record or manual evidence-based entry, clearly labeled | Unrecorded cash is not inferred from bank deposits |
| Job profitability | Match order ID to materials, labor, discounts, reprints, allocated overhead assumptions | Missing job costs produce unknown margin, not a fabricated margin |
| Unsupported platforms | Compatibility registry: official API, accounting feed, bank feed, report export, manual; disclose coverage gaps | Onboarding shows supported and unsupported features per platform |
| Data correction & audit | Versioned corrections, import receipts, user/time/source attribution | Reversal can be traced to original source and actor |
| Disaster recovery | Automated encrypted backups, restoration rehearsals, recovery targets | Restore sample tenant in isolated environment and reconcile totals |
| Availability & monitoring | Health checks, job monitoring, error tracking, client-facing stale-data warnings | Failed sync generates alert and dashboard shows stale timestamp |
| Client onboarding | Source mapping, permission consent, coverage confirmation, reconciliation checklist | New client can connect or import without misleading profit |
| Security engineering | Threat model, secrets management, dependency scanning, penetration test, incident playbook | No unresolved critical/high issues; incident drill completed |

## P2 — Improvements after a controlled pilot
- Advanced supplier pricing and waste analysis only with evidenced baselines.
- Predictive alerts only after backtesting false positives and providing explanation.
- Custom legacy connectors only after documented vendor approval, feasibility and cost.
- Billing and subscriptions with reliable entitlements, cancellation and invoicing.
- Accessibility, performance, mobile usability and clear support processes.

## Platform-specific fallback ladder
1. Official merchant-authorized API (Square, Stripe, eligible providers).
2. Accounting connector (e.g., QuickBooks) with explicit deduplication.
3. Authorized bank transaction feed for cash movements; **not** a substitute for itemized sales.
4. Exported CSV/XLSX or scheduled emailed reports, with permission and validation.
5. Limited manual entry with review, audit trail and explicit completeness status.
6. If no trustworthy records exist, **do not offer verified profitability or job-margin features**.

## Specific code changes to prioritize
- ~~`app.py`: prohibit confidential uploads in demo; add coverage/completeness confirmation and unavailable profit states; use exact Decimal monthly grouping.~~ Closed 2026-10-20: the older Ledger screen in `app.py` was retired; `app.py` now opens only the MargenX page.
- ~~`app.py` import reader: read money fields as text to avoid binary floating-point round trips.~~ Closed with the same change (MargenX's intake reads money as text).
- `data_pipeline.py`: add source namespace, currency, timezone, external ID and validation reporting.
- `finance_engine.py`: require a completeness flag for verified profit; distinguish provisional vs verified calculations.
- New storage layer: tenant ID, canonical records, immutable source references, import batches and idempotency keys.
- Tests: money precision, overlapping files, repeated uploads, refunds, reversals, multi-source reconciliation, source gaps, access isolation, sync replay, and restore.

## Pilot exit criteria
- Synthetic integration tests and continuous integration pass with visible run evidence.
- Owner-approved historical period reconciles to source reports with documented differences.
- Permission boundary and security tests pass.
- Simulated sync outage and backup restoration pass.
- Client understands verified/provisional/unavailable states.
- No unresolved critical/high defects.

**Do not mark any item complete without a link to its test evidence or verified implementation.**
