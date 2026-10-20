# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-20 (afternoon ET),** from GitHub (`main` at `4150214`, open PRs, issue and PR comments) and the owner's decisions in Claude Code sessions. **[unverified]** marks anything not read from GitHub or `main`.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins. Say so in your handoff, and refresh this file in a docs-only PR. **New sessions: read this file, `AGENTS.md`, `docs/DECISIONS.md` and `docs/MVP_SPEC.md` first.** Don't rely on chat history or summaries.

## The product in one paragraph
**MarginX** (renamed from Ledger on 2026-10-18; the website draft spells it "MargenX", and the owner hasn't decided which) shows small Miami **print, sign and apparel shops** (2–15 people) which jobs and customers make or lose money. It uses the sales/invoice and cost/bill CSVs they already export from QuickBooks or Square. Owner decision 2026-10-20: **focus on this niche only**, not "any business". Expanding to other job-based businesses comes later, if the niche works.

## Who does what
- **Owner (Alex, GitHub MrTooi):** decides and approves every merge. He's new to coding, so explain things in plain language with one clear next step.
- **Partner (Abrey):** customer conversations, pilot recruitment and the website. Due: a note on which software and exports shops use (**Wed 2026-10-21**), then a summary and pilot candidates (**Fri 2026-10-23**). Emails with the plan and the conversation guide were sent Oct 18, 19 and 20.
- **Claude Code:** builds, tests and writes the reviews' fix lists. **ChatGPT:** independent review (D-004).

## How work is done
Branch → tests (`~/.venvs/miami-sales-demo/bin/python -m unittest discover -s tests` on the Mac; Python 3.11) → PR → automated ChatGPT screening → **manual ChatGPT review** (the owner pastes Claude's message into ChatGPT and posts the verdict as a PR comment) → owner merges. **D-005:** for MarginX import/label PRs while the data is fictional, manual reviews pass unless a defect can show a wrong figure as Complete for a common, realistic export layout; narrower cases go to `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`. `gh` isn't installed on the owner's Mac: give prefilled GitHub compare links for new PRs.

## What's built (all made-up data only)
| Piece | Where | Status |
|---|---|---|
| Step 1: CSV intake, column/date detection, questions instead of guesses, row-level rejections, "what's missing" report | `job_intake.py`, `pages/1_MarginX_Import.py` | Merged (#100) |
| Step 2: direct job contribution per job and customer; Complete / Provisional / Unavailable statuses; exact Decimal | `job_profit.py` | Merged (#102) |
| Step 3a: sit-down pilot safety (pilot mode on a laptop only, owner consent before upload, nothing saved, End session deletes uploads and confirms it, strict U.S. money parsing, `marginx_pilot.py` entry point, legacy Ledger app off in pilot mode) | `pilot_safety.py`, `docs/PILOT_VISIT_CHECKLIST.md` | Merged (#104) |
| Demo sign shop (fictional, tells a clear story) | `sample_data/marginx/demo_sign_shop_*.csv` | Merged (#106) |
| D-005 review stopping rule plus the real-export follow-up list | `docs/DECISIONS.md`, `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md` | Merged (#103) |
| Shop conversation guide | `docs/SHOP_CONVERSATION_GUIDE.md` | **PR #105 open**, waiting for the owner to merge (docs only) |
| **Redesign:** results-first dashboard in the website's light mint/green style. Headline numbers, "what needs your attention" (losing jobs with break-even and usual-margin prices, thin jobs, thin biggest customer, jobs to check), customers ranked by what they leave, clickable job and customer breakdowns, "after overhead" line, "so far" margins on jobs that need a check | `marginx_ui.py`, `marginx_insights.py`, branch `marginx/redesign` | **Pushed; its PR isn't created yet.** 655 tests pass. |

## What is NOT proven or handled yet
- **No real shop export has ever been run.** Everything is tested on fictional files, and "what owners want" is our assumption until conversations confirm it.
- Known gaps (see `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`):
  - the exact QuickBooks/Square layouts
  - bills without job numbers
  - labor paid as wages, not per job (would make most jobs "needs a check")
  - Excel files
  - sales tax
  - card/processing fees
  - date coverage across files
  - inventory vs. cost of goods sold
  - quoted vs. actual
  - apparel shops that sell products rather than jobs
  - Spanish
- The website draft claims things MarginX doesn't do yet (Excel, labor hours, quoted vs. actual, card fees, the "change what happened" sliders). Fix them before it goes public.
- **Real customer data is prohibited** until step 3b is done and the owner records **D-006** (real data approved for a named pilot shop).

## Next actions, in order
1. **In progress:** Claude's accuracy self-tests, requested by the owner:
   - an independent integer-cents calculator compared with MarginX on the demo and test files
   - thousands of random fictional shops with known answers
   - on-screen figures checked against the engine
   - one job worked through by hand for the owner
2. Create the redesign PR (`marginx/redesign`), then review and merge. Merge PR #105.
3. Owner decisions pending:
   - the name (MarginX or MargenX; it's the `BRAND` constant in `marginx_ui.py`)
   - whether to build the Opportunity Radar **evidence store** (issue #1), proposed so conversation notes become scored evidence
   - where Abrey records notes (a Google Sheet, or a page Claude builds)
4. After Abrey's software note: **step 3b**, the real export layouts plus the high-priority follow-ups, guided by what shops actually use. Candidates to validate in conversations first: labor hours × rate (as an estimate), how-to-export instructions, profit by product type, quoted vs. actual.
5. D-006, then the first sit-down pilot visit, following `docs/PILOT_VISIT_CHECKLIST.md`. Repeat the real upload-and-delete browser test before it.

## Paused or background
- **AI-team readiness gate** (Suites A/B/C, #11/#69/#35): paused by the owner's choice (focus on MarginX). The round-3 Suite A scheduled run `39175749268` (2026-10-18, at `34e43ee`) **failed** and is **not recorded on #69**. Every scheduled run since refuses at "Require reviewed hardening change" (expected; no paid call). A→B→C successes: 0. Unattended agents stay disabled.
- **Opportunity Radar:** the scoring foundation is on `main` (`opportunity_radar/`); the evidence store (issue #1) isn't built.
- Draft PRs #16 (old LEDGER website), #39/#62/#63/#64 (trial evidence) and #67/#70 (old readiness drafts) stay unmerged on purpose.
