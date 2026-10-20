# Miami print/service shops: how they run, and what MarginX needs

- **Date:** 2026-10-18. **Author:** Claude Code, at the owner's request.
- **Product name:** the owner renamed Ledger to **MarginX** on 2026-10-18. The repo still says "Ledger" until a rename PR lands.
- **Evidence level:** desk research only (vendor pages, community forums, Census, law-firm summaries). That is level 7–10 on the evidence hierarchy in `.github/copilot-instructions.md`. **None of this is customer evidence.** Every item marked *inference* or *verify* must be checked with real shops before we rely on it.

## 1. The market around us (observed)
- **Firm counts:** Miami-Dade had **83,164 employer firms** (2023), 50,292 of them minority-owned, plus **748,628 nonemployer establishments** (mostly one-person businesses). [Census QuickFacts](https://www.census.gov/quickfacts/fact/table/miamidadecountyflorida/NES010223)
- **Population:** 70.6% of the county is Hispanic or Latino (2025 estimate). [Census QuickFacts](https://www.census.gov/quickfacts/fact/csv/miamidadecountyflorida/RHI725225)
- *Inference:* a meaningful share of pilot owners will prefer Spanish, or Spanish and English. **Verify** with the first shops.

## 2. How small print/sign shops track jobs and money (observed)
- **Shop software:** dedicated systems exist, such as [shopVOX](https://www.capterra.com/compare/155218-210917/shopVOX-vs-ePs-PrintSmith-Vision) (listed from about $99/mo, with job costing and QuickBooks integration), [Printavo](https://www.getapp.com.au/compare/110507/2065405/shopvox/vs/printavo) and PrintSmith Vision. Many small shops may use only QuickBooks plus spreadsheets. *Verify:* we don't know the local mix.
- **QuickBooks Online exports:** QBO has project profitability reports, but they export **one project at a time to Excel** and there is no direct CSV. Support suggests combining the "Project Profitability Summary" and "Project Cost Detail" exports by hand. [QuickBooks community](https://quickbooks.intuit.com/learn-support/en-us/reports-and-accounting/export-reports/00/1277391), [QB support thread](https://quickbooks.intuit.com/community/reports-and-accounting-5/project-profitability-reporting-60965)
- **Square exports:** the Transactions CSV has fee and net columns. "Net collected" **excludes cash**. Column layouts have changed over time, and loan repayments appear under deposits, not as fees. [Square community](https://community.squareup.com/t5/Product-Updates/Improvement-Transactions-Report-Enhancements/m-p/639958)
- **Job-costing gaps:** labor is usually the hardest cost to pin down. Materials are bought by several people across several jobs. Many small firms cost jobs from materials only and leave labor out. The sources are vendor and consultant blogs (construction-heavy), so treat them as directional. [QuickBooks survey](https://quickbooks.intuit.com/resources/construction-job-costing-survey), [B2B CFO](https://www.b2bcfo.com/shane-campbell/you-can-only-manage-what-you-measure/)

## 3. Rules for holding their data (observed; needs a lawyer before real data)
- **Florida's breach law (FIPA, Fla. Stat. § 501.171) applies to businesses of any size** that hold Florida residents' personal information.
  - Individuals must be notified within **30 days** of determining a breach.
  - The Attorney General must be notified at **500+** affected residents, and credit bureaus at **1,000+**.
  - There are vendor (third-party agent) duties. Secondary sources mention a 10-day notice from vendor to business. **Verify** this against the statute; the 2024 amendments are not reviewed here.
  - Sources: [Colodny Fass](https://colodnyfass.com/blog/florida-information-protection-act-of-2014-explained-data-breach-notification-and-protection-requirements-for-certain-entities), [Ashurst Perkins Coie](https://www.ashurstperkinscoie.com/en/insights/security-breach-notification-chart---florida/)
- *Inference:* MarginX would be the shop's vendor. Before any real data:
  - a short written data agreement with the pilot shop;
  - collect the minimum (no card numbers, SSNs or bank logins);
  - delete on request;
  - a review by a Florida attorney.

  This matches the existing `LAUNCH_RISK_REGISTER.md` minimums and D-003 (real data needs an explicit owner decision).

## 4. Who can introduce us to shops (observed)
- **Florida SBDC at FIU:**
  - free consulting for Miami-Dade and Monroe businesses, generally with **3+ employees**; helped 8,000+ entrepreneurs over 10 years;
  - runs a Small Business Resource Navigator program with partners including the Miami-Dade Chamber of Commerce, Prospera, Ascendus, Branches and the Economic Development Council of South Miami-Dade.
  - Sources: [FIU news](https://news.fiu.edu/2024/cheers-to-10-years-of-small-business-impact-how-florida-sbdc-at-fiu-came-to-be), [FIU Business](https://business.fiu.edu/news/2021/fiu-receives-2-5-million-sba-grant-to-help-local-businesses.html)
- **Florida Graphics Alliance**, formerly the Printing Association of Florida: a statewide association for printers and sign, graphics and apparel shops, offering events and education. [floridagraphics.org](https://www.floridagraphics.org/who-we-are)
- **Graphics of the Americas**, a printing trade show associated with the Florida association. Location and dates: **verify**. [piworld](https://piworld.com/article/graphics-americas-printing-trade-show-registration-now-open/2)
- *Inference:* **bookkeepers and accountants** who serve small shops are a likely channel, because they already produce the exports. Not researched; **verify**.

## 5. What MarginX must handle (the checklist)

**Getting data in**
- [ ] Upload **CSV and Excel (.xlsx)**, because QBO exports to Excel. No logins to their systems in the pilot.
- [ ] Combine **several files**: invoices, bills or expenses, payments, and optionally time sheets. Also handle QBO per-project files.
- [ ] A **"map your columns"** step for unfamiliar layouts. Remember mappings per shop.
- [ ] Square-type data:
  - fees as costs;
  - **payouts and deposits are cash movement, not revenue**;
  - cash sales are missing from "net collected";
  - dedupe on transaction ID.
- [ ] Structure checks before trusting values; bad rows reported with reasons, never dropped.

**Breaking it down**
- [ ] Link costs to jobs by job number, customer and date. **Ask the owner** when unsure; never guess silently.
- [ ] An **"unassigned costs"** list the owner can sort into jobs.
- [ ] **Labor**: use hours if they exist; otherwise an owner-set estimate, clearly labeled.
- [ ] Profit per job and per customer in exact decimals. Mark **"incomplete"** when key costs are missing.
- [ ] A "what's missing" report written in plain language.

**Working with owners**
- [ ] **English and Spanish** UI and reports (*verify demand*).
- [ ] Hands-on pilot: the partner sits with the owner, exports the files together, and we return a first report quickly.
- [ ] A shareable view for their bookkeeper (*verify*).

**Safety before real data**
- [ ] Pilot safety minimums (D-003(e)), a written pilot agreement, a Florida attorney review of data handling, and an owner decision.

## 6. Questions the partner should ask 3–5 shops
The full, current list is in `docs/SHOP_CONVERSATION_GUIDE.md`.
1. What software do you use for quotes, jobs, invoices and expenses?
2. Do you track costs or hours per job? How?
3. Can you export to CSV or Excel? Ask them to describe it or show the screen. **Don't take any file, not even an anonymized one**: until step 3 and the owner's approval of real data, only made-up data is allowed (D-003, `docs/MVP_SPEC.md`).
4. English, Spanish, or both?
5. Do you have a bookkeeper or accountant? Would they need to see this?
6. What would make a weekly profit report worth paying for?
