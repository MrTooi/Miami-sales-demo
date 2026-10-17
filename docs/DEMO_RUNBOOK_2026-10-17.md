# Ledger Demo Runbook — Oct 17, 2026

## Goal
Deliver a reliable 5–7 minute Ledger demo using the existing fictional sample data and current product behavior on `main`. Do not depend on unproven live integrations or confidential customer data.

## Pre-demo checks
1. Confirm repository CI on `main` is green.
2. Launch the existing Streamlit app from the repository root:
   ```bash
   streamlit run app.py
   ```
3. Confirm the app opens with the fictional demo dataset and shows `DEMO SAMPLE` rather than a live/verified customer state.
4. Click through all four tabs once before the meeting: Overview, Costs, Transactions, Data health.
5. Keep a browser tab open on the demo before the meeting starts.
6. Have a local clone/run available as the fallback if hosted access fails.

## 5–7 minute demo flow

### 1. Opening — 30 seconds
Say:
> Ledger is a financial intelligence system for business owners. The goal is to turn raw sales and expense records into a clear view of what changed, where costs are moving, and what needs attention. What you are seeing today is a development demo using fictional sample data.

Do not say that Ledger is production-ready, commercially validated, or connected live to every provider.

### 2. Overview — 2 minutes
Stay on **Overview**.

Show:
- reporting period selector
- `NET REVENUE`
- `GROSS PROFIT`
- `OPERATING PROFIT`
- `REFUNDS`
- revenue trend chart
- exact monthly totals
- operating snapshot

Key line:
> Ledger separates revenue from profit and withholds profit when expense coverage is incomplete. It does not treat deposits or payouts as new revenue.

If asked whether the chart is bank balance, say no. The chart is net revenue activity, not cash balance.

### 3. Costs — 1 minute
Open **Costs**.

Show:
- direct costs
- operating expenses
- record observations
- source/basis text under each observation

Key line:
> The point is not to generate generic AI advice. Ledger ties an observation back to the records that support it and avoids inventing savings claims.

### 4. Transactions — 45 seconds
Open **Transactions**.

Show:
- underlying sales records
- expense records
- CSV export buttons

Key line:
> Every headline should be traceable back to the underlying records. Owners should be able to ask, “Why does Ledger say this?” and inspect the evidence.

### 5. Data health — 1 to 1.5 minutes
Open **Data health**.

Explain:
- fictional demo data does not represent a real customer
- uploaded anonymized data can exercise duplicate/conflict/reconciliation paths
- unresolved conflicts should remain visible
- transfer reconciliation is separate from revenue recognition

Key line:
> Ledger is designed to show uncertainty instead of hiding it. If data is incomplete or unreconciled, the system should say that rather than manufacture confidence.

### 6. Close — 30 seconds
Say:
> The next stage is making this workflow reliable across real business data sources, then proving the recommendations are useful enough that businesses will pay for them. We are deliberately testing the trust layer before we make stronger claims.

## Questions we can answer safely

### “Can this connect to Square or QuickBooks?”
Say:
> That is the intended direction. The current demo supports structured imports and source-aware handling; live production connectors are not being represented as complete today.

### “Is this real customer data?”
Say:
> No. Today’s demo is fictional sample data.

### “Is the profit number guaranteed accurate?”
Say:
> No. Ledger’s design is to make profit conditional on having enough expense coverage and to surface incomplete data rather than overstate certainty.

### “Is the AI making the financial calculations?”
Say:
> No. Core financial calculations are deterministic. AI is intended to explain and prioritize evidence, not rewrite the underlying numbers.

### “Are you production-ready?”
Say:
> Not yet. This is a development demo. We are completing readiness, data-integrity, and real-business validation before we call it production-ready.

## Claims to avoid
Do not claim any of the following unless new verified evidence exists before the meeting:
- real customer revenue or customer count
- guaranteed savings or ROI
- paid validation
- production readiness
- live direct integration with a provider that is not actually connected
- bank-grade security
- HIPAA compliance
- full accounting replacement
- every number is verified in all circumstances
- autonomous AI is already cleared for unrestricted product work

## Backup plan
If the primary demo path fails:
1. Use a local Streamlit run from a clean checkout of `main`.
2. Use the fictional sample data only.
3. If a specific tab fails, skip it and continue the story with the remaining working tabs rather than debugging live in front of the audience.
4. Keep the explanation honest: this is a development demo and a failed non-core surface is not evidence the underlying financial result is verified.

## Demo-ready acceptance checklist
- [ ] `main` CI green
- [ ] app launches from `streamlit run app.py`
- [ ] fictional demo opens without upload
- [ ] `DEMO SAMPLE` visible
- [ ] Overview renders
- [ ] Costs renders
- [ ] Transactions renders
- [ ] Data health renders
- [ ] revenue trend has exact monthly totals available
- [ ] no confidential customer data loaded
- [ ] local fallback available
- [ ] presenter rehearses the 5–7 minute flow once end-to-end

## Scope freeze for tonight
Do not add new financial/product behavior just to make the demo look broader. Prefer reliability, clarity, and a smooth story over feature count. The Agent OS A→B→C gate continues independently and is not weakened for the demo.
