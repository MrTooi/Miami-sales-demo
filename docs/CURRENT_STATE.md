# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-20 (late evening ET),** from GitHub (`main` at `e08379f`, after PR #116; open PRs, issue and PR comments) and the owner's decisions in Claude Code sessions. **[unverified]** marks anything not read from GitHub or `main`.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins. Say so in your handoff, and refresh this file in a docs-only PR. **New sessions: read this file, `AGENTS.md`, `docs/DECISIONS.md` and `docs/MVP_SPEC.md` first.** Don't rely on chat history or summaries.

## The product in one paragraph
**MargenX** (renamed from Ledger on 2026-10-18; the owner settled the spelling **MargenX**, one word, matching the website, on 2026-10-20 in PR #109) shows small Miami **print, sign and apparel shops** (2–15 people) which jobs and customers make or lose money. It uses the sales/invoice and cost/bill files they already export from QuickBooks or Square, as CSV or Excel (.xlsx), including report-style exports (#116). Owner decision 2026-10-20: **focus on this niche only**, not "any business". Expanding to other job-based businesses comes later, if the niche works.

## Who does what
- **Owner (Alex, GitHub MrTooi):** decides and approves every merge. New to coding and to running a company: explain code *and* business terms (margin, overhead, break-even) in plain language, with one clear next step.
- **Partner (Abrey):** customer conversations, pilot recruitment and the website. Due: a note on which software and exports shops use (**Wed 2026-10-21**), then a summary and pilot candidates (**Fri 2026-10-23**). Emails with the plan and the conversation guide were sent Oct 18, 19 and 20. The owner shared the demo page and the decks with Abrey on 2026-10-20 **[unverified]**.
- **Claude Code:** builds, tests and writes the reviews' fix lists. **ChatGPT:** independent review (D-004).

## How work is done
Branch → tests (`~/.venvs/miami-sales-demo/bin/python -m unittest discover -s tests` on the Mac; Python 3.11) → PR → automated ChatGPT screening → **manual ChatGPT review** (the owner pastes Claude's message into ChatGPT and posts the verdict as a PR comment) → owner merges. When a manual review is required is set by D-004 in `docs/DECISIONS.md`, not by this snapshot. **D-005:** for MargenX import/label PRs while the data is fictional, manual reviews pass unless a defect can show a wrong figure as Complete for a common, realistic export layout; narrower cases go to `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`.
- `gh` works on the owner's Mac (used throughout 2026-10-20).
- On #116 the automated review stayed FAIL on one item that the manual review classed as a D-005 warning. The owner reconciled the two and approved the merge; both are recorded on the PR.
- **Merging needs an up-to-date branch:** `main` has a GitHub *ruleset* (not classic branch protection, so `branches/main/protection` returns 404) that refuses a PR branch that is behind `main`. Run `gh pr update-branch <n>`, wait for CI and the automated review, then `gh pr merge <n> --merge --match-head-commit <sha>`. Never use `--admin`.

## What's built (all made-up data only)
| Piece | Where | Status |
|---|---|---|
| Step 1: CSV intake, column/date detection, questions instead of guesses, row-level rejections, "what's missing" report | `job_intake.py`, `pages/1_MargenX_Import.py` | Merged (#100) |
| Step 2: direct job contribution per job and customer; Complete / Provisional / Unavailable statuses; exact Decimal | `job_profit.py` | Merged (#102) |
| Step 3a: sit-down pilot safety (pilot mode on a laptop only, owner consent before upload, nothing saved, End session deletes uploads and confirms it, strict U.S. money parsing, `marginx_pilot.py` entry point, legacy Ledger app off in pilot mode) | `pilot_safety.py`, `docs/PILOT_VISIT_CHECKLIST.md` | Merged (#104) |
| Demo sign shop (fictional, tells a clear story) | `sample_data/marginx/demo_sign_shop_*.csv` | Merged (#106) |
| D-005 review stopping rule plus the real-export follow-up list | `docs/DECISIONS.md`, `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md` | Merged (#103) |
| Shop conversation guide | `docs/SHOP_CONVERSATION_GUIDE.md` | Merged (#105) |
| **Redesign:** results-first dashboard in the website's light mint/green style (see "What the redesign shows" below) | `marginx_ui.py`, `marginx_insights.py`, `pages/1_MargenX_Import.py` | Merged (#108). Automated review PASS WITH WARNINGS; ChatGPT manual review round 1 **FAIL**, round 2 **PASS WITH WARNINGS** (both recorded as PR comments). 681 tests. |
| **Rename to MargenX:** header, tab title, page file (`pages/1_MargenX_Import.py`), consent text, messages, shop-facing docs | many files (text only) | Merged (#109). Automated review PASS. |
| **Older Ledger screen retired** (owner decision 2026-10-20): `streamlit run app.py` opens only the MargenX page, at the main address `/` (the same as `marginx_pilot.py`). The old dashboard and `ui_theme.py` are removed; shared code (`finance_engine.py`, `data_pipeline.py`, `ledger_store.py`, `app_ledger.py`) stays because MargenX or the paused readiness tooling uses it | `app.py` | Merged (#111). ChatGPT manual review PASS WITH WARNINGS. |
| **Static demo page** of the made-up demo shop: no server, no uploads (D-006). PR #112 (a hosted Streamlit demo) was closed after the manual review found Streamlit always exposes an upload endpoint | `scripts/build_demo_page.py`, `docs/DEMO_LINK.md` | Merged (#113). ChatGPT manual review PASS WITH WARNINGS. Published as a private page the owner shares **[unverified]**. |
| **Real MargenX logo** in the app header, tab icon and demo page | `assets/margenx-logo.png` | Merged (#114). The owner checks images by eye; the automated reviewer can't see them. |
| **Accuracy self-tests:** an independent calculator in cents (no MargenX code), 400 made-up shops in CI and 5,000 in a script, an on-screen figure check, 6 planted bugs all caught, and one job worked by hand | `tests/accuracy_shops.py`, `tests/test_accuracy.py`, `scripts/accuracy_check.py`, `scripts/accuracy_mutations.py`, `docs/ACCURACY.md` | Merged (#115). Results are for made-up shops only. |
| **Excel (.xlsx) and report-style files:** numbers read from the exact stored text, never rounded while reading; title lines skipped; total, heading and footer rows skipped only when proven, everything unclear rejected as possibly missing money; size, unpacked-size and shape limits | `job_intake.py` (`read_file`), `tests/test_file_reading.py` | Merged (#116). Tested on made-up files only. Automated review FAIL on one item (numbered title lines like "Paid 500"); ChatGPT manual review **PASS WITH WARNINGS**, no blockers; the owner accepted that item as a D-005 follow-up. 723 tests. |

### What the redesign shows (#108)
As implemented and tested in #108 (regression tests in `tests/test_marginx_ui.py`, `tests/test_marginx_insights.py`, `tests/test_marginx_import_page.py`), and reviewed in the ChatGPT manual review round 2. This summary is not itself evidence. The rule behind it: **a number that is incomplete says so, or isn't shown.**
- **Headline cards** say which jobs they cover ("From 3 of 7 jobs" / "From all 8 jobs") and disclose sales with no job number and rows that couldn't be read.
- **Jobs losing money** counts only jobs with complete costs. A job that needs a check and shows a loss so far reads "**may have** lost $X", with its real reason.
- **After overhead:** "After $X of costs not tied to any job, these files leave $Y" appears only when every sale is in the job total and no row was rejected. Otherwise it is withheld, and the page says what's left out. Overhead (rent, fees) is kept apart from costs with no job number.
- **Biggest customer** finding: compared only against customers with complete figures, and qualified when a bigger customer may be hidden. Break-even is "to cover its job costs (before overhead not assigned to this job)". The usual margin is the share of sales kept across complete jobs (sales-weighted, not an average).
- **Outside web requests:** the page's own styles load no web fonts, and file text can't inject Markdown images or links (`marginx_ui.md_text`, one-line HTML blocks). In one fresh-browser check at `7811bb4` on 2026-10-20, all 134 requests went to localhost. That's a single manual check, not an audit of every path.

### Names that intentionally keep the old spelling
Internal code names (`marginx_ui.py`, `marginx_insights.py`, `marginx_pilot.py`, `MARGINX_PILOT`, branch names), `docs/DECISIONS.md` (history), `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md` (file name), and `command_center/` (it counts past PRs titled "MarginX step N"). **`docs/CHATGPT_REVIEW_INSTRUCTIONS.md` still says "MarginX"**: it's the reviewer's prompt, so changing it is the owner's call.

## What is NOT proven or handled yet
- **No real shop export has ever been run.** Everything is tested on fictional files, and "what owners want" is our assumption until conversations confirm it.
- Known gaps (see `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`):
  - the exact QuickBooks/Square layouts. Excel and report-style reading (#116) is built and tested on made-up files only: the QuickBooks Online test drive was down, so no real report has been seen. The checks to do on a real file are in item 6 of that doc.
  - bills without job numbers
  - labor paid as wages, not per job (would make most jobs "needs a check")
  - sales tax
  - card/processing fees
  - date coverage across files
  - inventory vs. cost of goods sold
  - quoted vs. actual
  - apparel shops that sell products rather than jobs
  - Spanish
- **Money amounts are capped (this PR, `margenx/money-length-cap`):** `finance_engine.money` refuses any amount over $999,999,999,999.99 either way, with its own reason, so sums stay exact under Python's 28-digit Decimal precision (a test adds a billion capped amounts with rounding trapped). Before this, an absurdly long amount (30+ digits) could have been rounded when added up. Found during #116. This is finance logic, so it needs the manual review (D-004).
- **"Complete" means complete per the imported files** (sales, labor, and materials or outsourced work present, nothing rejected), not reconciled business profit. MargenX can't know about costs that were never recorded.
- The website draft claims things MargenX doesn't do yet (labor hours, quoted vs. actual, card fees, the "change what happened" sliders). Fix them before it goes public. Excel reading now exists (#116), but only on made-up files.
- **Real customer data is prohibited** until step 3b is done and the owner records the real-data decision (**D-007 or later**; real data approved for a named pilot shop).

## Next actions, in order
1. After Abrey's software note (due Wed 2026-10-21): **step 3b**, the real export layouts plus the high-priority follow-ups, guided by what shops actually use. Get one real QuickBooks Online report **layout** first (the column names and row shapes, for example from the QuickBooks test drive or an export filled only with made-up entries, **not** a shop's real records): it confirms or corrects #116. Real customer data stays prohibited until the owner's real-data decision is recorded. Candidates to validate in conversations first: labor hours × rate (as an estimate), how-to-export instructions, profit by product type, quoted vs. actual.
2. Small follow-ups (non-blocking):
   - clamp the customer sales-bar width for a customer with net-negative sales (cosmetic; from the #108 review)
   - optional test additions from the #113 and #115 reviews (see those PRs)
   - **owner decision:** whether to update `docs/CHATGPT_REVIEW_INSTRUCTIONS.md` to the new name (it still says "MarginX" once)
3. Other owner decisions pending:
   - whether to build the Opportunity Radar **evidence store** (issue #1, open), proposed so conversation notes become scored evidence
   - where Abrey records notes (a Google Sheet, or a page Claude builds)
4. The real-data decision (D-007 or later), then the first sit-down pilot visit, following `docs/PILOT_VISIT_CHECKLIST.md`. Repeat the real upload-and-delete browser test before it, now with an Excel file too.

## Paused or background
- **AI-team readiness gate** (Suites A/B/C, #11/#69/#35): paused by the owner's choice (focus on MargenX). The run details below are from the earlier snapshot and weren't re-checked on 2026-10-20 evening; #69 is still open. The round-3 Suite A scheduled run `39175749268` (2026-10-18, at `34e43ee`) **failed** and is **not recorded on #69**. Every scheduled run since refuses at "Require reviewed hardening change" (expected; no paid call). A→B→C successes: 0. Unattended agents stay disabled.
- **Opportunity Radar:** the scoring foundation is on `main` (`opportunity_radar/`); the evidence store (issue #1) isn't built.
- Draft PRs #16 (old LEDGER website), #39/#62/#63/#64 (trial evidence) and #67/#70 (old readiness drafts) stay unmerged on purpose.
