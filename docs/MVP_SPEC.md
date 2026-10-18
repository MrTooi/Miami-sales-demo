# MarginX pilot MVP: 1-page spec

**Status:** draft for review (#92). **Scope source:** D-003 in `docs/DECISIONS.md`.

The owner renamed the product from Ledger to **MarginX** on 2026-10-18. Code and other docs still say Ledger until a separate rename PR lands. Market notes come from `docs/research/MIAMI_SHOP_RESEARCH.md` (PR #95), which is desk research only, not customer evidence.

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

- **Formats:** CSV and Excel (.xlsx), several files at once.
- **Columns:** the owner maps any unfamiliar columns once, and MarginX remembers the mapping per shop.

## What they see
1. **"What's missing" report (step 1, this week).** Plain-language gaps with counts, for example:
   - "40 of 120 jobs have no cost recorded."
   - "No labor hours found."
   - "15 bills aren't linked to a job."
   - "6 rows rejected: missing amount (rows listed)."
2. **Profit by job and by customer.**
   - Revenue minus materials, outsourced work and labor.
   - Any job missing key costs is marked **incomplete** and its profit is withheld, not shown as a number.
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

None of these has been measured yet; they are targets, not results.

## Build order (each step is one small PR, tested, independently reviewed, owner-approved)
1. **Upload + "what's missing" report.** CSV/XLSX, column mapping, structure checks, rejected-row list. It reuses `data_pipeline.normalize`, `transaction_integrity.deduplicate` and the Decimal helpers in `finance_engine`.
2. **Profit by job and customer**, with incomplete jobs flagged. This extends `finance_engine.summarize` (`expenses_complete`).
3. **"Where you're losing money" list.**
4. **Weekly summary.**
5. **Pilot data-safety minimums** (can run alongside 1–4).

## Out of scope for the pilot
- Live QuickBooks/Square/bank connections (they need credentials and a separate owner decision).
- Pricing, production deployment, and real customer data before (5).

## Open questions (answers come from the partner's conversations)
- Which software and export layouts are most common locally?
- Do shops have a job ID that appears on both invoices and bills?
- Is Spanish needed from day one?
