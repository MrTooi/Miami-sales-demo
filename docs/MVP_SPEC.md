# MargenX pilot MVP: 1-page spec

**Status:** draft for review (#92). **Scope source:** D-003 in `docs/DECISIONS.md`.

The owner renamed the product from Ledger to **MargenX** on 2026-10-18. Code and other docs still say Ledger until a separate rename PR lands. Market notes come from `docs/research/MIAMI_SHOP_RESEARCH.md` (PR #95), which is desk research only, not customer evidence.

## Who it's for
- **Customers:** owners of small, job-based print, sign and apparel-printing shops in Miami-Dade, roughly 2–15 people.
- **Their situation:** they invoice per job but rarely track costs or labor per job, so they don't know which jobs or customers make money.
- **To confirm:** the partner's shop conversations this week test this assumption.

## What they upload (pilot: files only, no logins)
| File | Required? | Typical source |
|---|---|---|
| Sales / invoices (date, customer, job or invoice ID, amount) | Yes | QuickBooks, Square, print-shop software |
| Costs / bills / expenses (date, vendor, amount, optional job ID or memo) | Yes, for any profit | QuickBooks, bank or card export |
| Labor hours per job | Optional | Time sheet or spreadsheet |
| Payment processor or bank deposits | Optional | Square, bank |

- **Formats:** CSV first (D-003). Excel (.xlsx), several files at once, and saved per-shop column mappings come in later reviewed steps, once coverage and provenance rules are defined.
- **Columns:** the owner maps unfamiliar columns to ours, and the mapping is validated before any value is used.
- **Bank and card exports:** these are never automatically treated as revenue or costs. Provider movements, fees, transfers and genuine expenses are told apart first, so nothing is double-counted (`LAUNCH_RISK_REGISTER.md`).

## What they see
1. **"What's missing" report (build step 1, this week).** Plain-language gaps with counts, for example:
   - "40 of 120 jobs have no cost recorded."
   - "No labor hours found."
   - "15 bills aren't linked to a job."
   - "6 rows rejected: missing amount (rows listed)."
2. **Profit by job and by customer**, for an explicitly stated date range and accounting basis.
   - **What the number is:** each result is labeled either **direct job contribution** (revenue minus materials, outsourced work and labor) or **fully allocated profit**. Adjustments (discounts, refunds, processor fees, reprints) and allocated overhead are included only with a defensible, stated method.
   - **When it's withheld:** if materials, labor, fees, refunds or allocation inputs are missing or unverified, the affected result is **unavailable or provisional**, never shown as exact profit. Optional labor hours do not make a result exact when labor is missing.
   - **Customer totals:** customer rollups inherit the incomplete-job warnings of their jobs.
3. **"Where you're losing money" list.**
   - Jobs priced below cost.
   - Customers whose margin is shrinking.
   - Costs that aren't linked to any job.
4. **Weekly owner summary.** What changed, the top money leak, and one thing to fix.

## Rules the product must follow (non-negotiable)
- **Exact money:** `Decimal` / cents everywhere, never floats.
- **Cash movement is not revenue:** payouts and bank deposits are never new revenue. Processor fees are costs.
- **Validate before trusting:** check a file's structure before trusting any values. Rejected rows are listed with reasons, never silently dropped or "fixed".
- **Never guess cost links:** the owner confirms uncertain job–cost links. Any labor estimate the owner sets is labeled "estimate".
- **Data:** fictional data only, until the pilot data-safety minimums (D-003(e), `LAUNCH_RISK_REGISTER.md`) are merged and the owner explicitly approves real data. Each shop's data stays separate.

## What "useful" means (pilot success)
- **Upload:** a pilot shop can upload its own exports in under 30 minutes, with help.
- **Found something new:** the owner sees at least one job, customer or cost gap they didn't know about, recorded in their own words in the #30 format.
- **Comes back:** the owner opens the weekly summary on 2 consecutive weeks.

None of these has been measured yet; they are targets, not results. Record actual outcomes, including contradicting feedback. Visits alone do not prove the product is financially useful.

## Build order (each step is one small PR, tested, independently reviewed, owner-approved)
1. **CSV upload + validated mapping + "what's missing" / rejected-row report.**
   - Build a **new** job/invoice/cost intake adapter, with a validated column mapping and a row-level rejection and coverage report.
   - Reuse the existing money parser and validators only where their input contracts fit.
   - Today's helpers are not a job importer. `data_pipeline.normalize` accepts only fixed `sales`/`expenses` schemas and raises on bad input instead of reporting rows. `transaction_integrity.deduplicate` needs canonical source-aware transaction events, so rows are converted to those events before it is applied.
   - Rows are never silently dropped or guessed.
2. **Profit by job and customer**, as defined above, from one sales CSV and one costs CSV linked by job number.
   - This is a **new** job/customer-keyed calculation on exact Decimal amounts.
   - `finance_engine.summarize` is a period-total helper with no job or customer grouping, not an existing job-profit engine.
   - Linking the two files needs only what is required for profit. Excel and saved mappings wait for step 4.
3. **Pilot data-safety minimums** (`LAUNCH_RISK_REGISTER.md`). After this, and only with the owner's explicit approval of real data, 1–2 pilot shops can use MargenX on their own files.
4. **Excel (.xlsx), more file combinations and saved per-shop mappings**, plus coverage and provenance rules.
5. **"Where you're losing money" list.**
6. **Weekly summary.**

**Order changed on 2026-10-19 by the owner:** the safety minimums moved ahead of the extra features, so a real pilot can start right after profit per job, and pilot feedback shapes steps 4–6. Until step 3 is done and the owner approves real data, MargenX is used with **made-up files only**; anonymized real exports are not allowed either.

## Out of scope for the pilot
- Live QuickBooks/Square/bank connections (they need credentials and a separate owner decision).
- Pricing and production deployment.
- Real customer data, until independently verified safety requirements are met and the owner explicitly approves it.

## Open questions (answers come from the partner's conversations)
- Which software and export layouts are most common locally?
- Do shops have a job ID that appears on both invoices and bills?
- Is Spanish needed from day one?
