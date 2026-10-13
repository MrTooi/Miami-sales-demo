# Project Brief — LEDGER + Opportunity Radar

Last updated: 2026-10-13

## Company goal

Find a recurring business problem that is painful, expensive, measurable, and poorly solved, then build software whose value clearly exceeds its price.

## Product hypotheses

### LEDGER

Customer-facing product hypothesis:

> A profit-intelligence layer that connects accounting, payment, banking, and operational data to show where a business makes or loses money, why it happens, what action to take, and whether the action worked.

Potential high-value capabilities include job profitability, quote-vs-actual analysis, profit-leak detection, pricing protection, owner briefs, action tracking, and ROI measurement.

LEDGER is **not** assumed to be validated yet. Commercial printing is a candidate beachhead, not a commitment.

### Opportunity Radar

Internal decision system used to discover, compare, challenge, and validate market opportunities.

Core principle:

> LEDGER must compete against every other opportunity. The research system is not allowed to protect our favorite idea.

Opportunity Radar separates:
- opportunity score,
- evidence confidence,
- supporting evidence,
- contradicting evidence,
- evidence quality/diversity,
- bull case,
- bear case,
- kill criteria,
- next cheapest validation experiment.

## Current team split

### Alex + ChatGPT / engineering lane

Own software architecture, implementation, tests, data models, persistence, integrations, security controls, AI-team infrastructure, and technical prototypes.

### Partner + Gemini / validation lane

Own market universe, pain-signal research, competitor intelligence, customer interviews, willingness-to-pay evidence, GTM/channel research, pricing research, pilot recruitment, partnership research, and business-side integration feasibility.

External research should become structured evidence that Opportunity Radar can ingest.

## Current technical state

### LEDGER prototype

Existing modules include:
- `finance_engine.py` — Decimal-based financial calculations and profit-availability rules.
- `data_pipeline.py` — strict sales/expense normalization and validation.
- `transaction_integrity.py` — transaction kinds, identity, deduplication, and movement-vs-revenue semantics.
- `ledger_store.py` — SQLite prototype persistence, import batches, conflicts, reconciliation links.
- `app_ledger.py` — app-to-integrity helper layer.
- `app.py` — Streamlit prototype dashboard.

The public demo is a prototype and is not suitable for confidential customer data.

### Opportunity Radar MVP

Current package:
- `opportunity_radar/models.py`
- `opportunity_radar/scoring.py`

The first scoring model is deterministic and has automated tests. It separates market attractiveness from confidence in the supporting evidence.

## Active development branch

`opportunity-radar-mvp`

The working LEDGER demo on `main` should not be destabilized while Opportunity Radar and the AI-team operating layer are developed.

## Immediate technical milestone

Build the **persistent evidence store + research import pipeline** so structured research from the partner/Gemini workflow can be ingested, validated, preserved with provenance, attached to opportunities, and used to recompute confidence/rankings.

Expected sequence after that:

1. Evidence persistence and import validation.
2. Opportunity repository and ranking.
3. Bull/bear and kill-criteria engine.
4. Internal research dashboard.
5. Carefully governed AI-assisted evidence extraction/summarization.
6. Customer/pilot evidence loops.

## Evidence hierarchy

Strongest to weakest:

1. Actual paid customer behavior.
2. Pilot behavior.
3. Signed commitment, deposit, or LOI.
4. Explicit willingness-to-pay evidence.
5. Customer interviews with quantified pain.
6. Existing spend/workarounds.
7. Software reviews.
8. Forums/community evidence.
9. Industry reports.
10. General speculation.

A high opportunity score with weak evidence must remain low-confidence.

## Product principles

- Value before polish.
- Trust before automation.
- Evidence before confidence.
- Prevent losses where possible, not only explain them after the fact.
- Make every important number traceable.
- Prefer a narrow painful workflow over a broad generic dashboard.
- Test willingness to pay through behavior, not compliments.
- Build concierge/manual versions before expensive automation when possible.

## Open strategic questions

- Which narrow vertical has the strongest recurring profit-visibility or operational-economics problem?
- Is job profitability the best wedge, or is quote protection more valuable?
- What data can target businesses realistically provide?
- Which buyer owns the pain and budget?
- What recurring output makes the product valuable every week?
- What contract value can be justified by measurable value created?
- Which distribution channel gives us trusted, affordable access to the buyer?

## Current rule for AI autonomy

AI agents may plan, implement on branches, test, review, document, and propose changes within repository policy.

Human approval remains required for production deployment, destructive operations, real credential/financial-data access, permission expansion, and high-risk merges.
