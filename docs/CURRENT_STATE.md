# Current State — SNAPSHOT (stale-able)

**Snapshot taken: 2026-10-26 (evening, Miami time),** from GitHub (`main` at `0d1478f`, after PR #129; open PRs, issue and PR comments) and the owner's decisions in Claude Code sessions. **[unverified]** marks anything not read from GitHub or `main`.

> **This file is a snapshot, not a source of truth.** Before acting, refresh from live GitHub and `main`. If anything here disagrees with them, GitHub/`main` wins. Say so in your handoff, and refresh this file in a docs-only PR. **New sessions: read this file, `AGENTS.md`, `docs/DECISIONS.md` and `docs/MVP_SPEC.md` first.** Don't rely on chat history or summaries.

## The product in one paragraph
**MargenX** (renamed from Ledger on 2026-10-18; the owner settled the spelling **MargenX**, one word, matching the website, on 2026-10-20 in PR #109) shows small Miami **job-based businesses** which jobs and customers make or lose money. It uses the sales/invoice and cost/bill files they already export from QuickBooks or Square, as CSV or Excel (.xlsx), including report-style exports (#116). Since #129, files that look like **QuickBooks reports are refused** with a plain message until they can be read safely (the plan is issue #128). **Target (D-007, owner decision 2026-10-22, recorded in #122):**
- print, sign and apparel shops
- trade contractors (remodeling, flooring and similar)
- custom makers and installers (cabinets, metal work and similar)

It isn't a product for every business. This replaces the 2026-10-20 "print shops only" focus.

## Who does what
- **Owner (Alex, GitHub MrTooi):** decides and approves every merge. New to coding and to running a company: explain code *and* business terms (margin, overhead, break-even) in plain language, with one clear next step.
- **Partner (Abrey):** outreach, booking meetings, and the website. **[unverified]**, from Claude Code sessions:
  - The customer plan was redone on 2026-10-22 after walk-in visits didn't lead to conversations. Abrey makes a short call (a few questions, no demo) and books a 30-minute meeting.
  - **Alex runs every meeting** and presents the slides and the demo page for that kind of business.
  - The plan, a starter lead list and the scorecard (decision date **Nov 13**) are in a claude.ai document shared with Abrey. They aren't in this repository.
  - The business contact email on the decks is margenxtech@gmail.com.
  - Abrey marks call outcomes with cell colours in the leads tab, not its Status column. His own Claude can't read that Claude Doc, so on 2026-10-26 he was emailed the doc's own Word export **[unverified]**.
- **Claude Code:** builds, tests and writes the reviews' fix lists. **ChatGPT:** independent review (D-004).

## How work is done
Branch → tests (`~/.venvs/miami-sales-demo/bin/python -m unittest discover -s tests` on the Mac; Python 3.11) → PR → automated ChatGPT screening → **manual ChatGPT review** (Claude writes the prompt, the owner pastes it into ChatGPT and pastes the answer back, and Claude records the verdict as a PR comment) → owner merges. When a manual review is required is set by D-004 in `docs/DECISIONS.md`, not by this snapshot. **D-005:** for MargenX import/label PRs while the data is fictional, manual reviews pass unless a defect can show a wrong figure as Complete for a common, realistic export layout; narrower cases go to `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`.
- `gh` works on the owner's Mac.
- The automated review uses the owner's OpenAI API credit. An HTTP 429 on review runs means the credit ran out: tell the owner to add credit (platform.openai.com → Billing).
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
| **Money cap:** `finance_engine.money` refuses any amount over $999,999,999,999.99 either way, with its own reason, so sums stay exact under Python's 28-digit Decimal precision | `finance_engine.py` | Merged (#118). Found during #116. |
| **Exact margin comparisons:** margins are kept and compared as exact fractions, so a near-tie is never decided by a cut-off decimal; only shown percentages and "about $X" prices are rounded | `marginx_insights.py` | Merged (#119). |
| **"How to read these numbers" note** under every result: exact sums, "Needs a check" may be missing costs, percentages rounded, prices are estimates, not accounting/tax/financial advice | `marginx_ui.py` (`READING_NOTE`) | Merged (#120). |
| **Pilot checklist matches the Free Pilot Agreement:** sign before any files; no cloud sync, backups or AI tools; Find My on; lost-laptop steps; tell the owner without waiting | `docs/PILOT_VISIT_CHECKLIST.md` | Merged (#121). The agreement and Privacy Notice are drafts kept as a Claude Doc **[unverified]**. |
| **Demos for each target group, and a clearer results page:** made-up remodeling contractor and cabinet/metal shop demos (in the app and as static pages); new tagline; **Profit margin** card; customer **table** instead of bars; margin on the after-overhead line; D-007 | `sample_data/marginx/demo_contractor_*`, `demo_custom_shop_*`, `marginx_ui.py`, `scripts/build_demo_page.py`, `docs/DECISIONS.md` | Merged (#122). ChatGPT manual review FAIL→fixed, then re-review **PASS WITH WARNINGS**. 746 tests. |
| **"Which job was this for?":** costs with no job number that may belong to a job are listed for the owner to match to a job, mark "Not for a job", or leave "Not sure yet" (the default; MargenX never picks). A costs file with no job column is read instead of refused. Answers are tied to both files' identity (name, exact bytes, every reading choice) and reset when either changes. The notes disclose every owner answer | `job_matching.py`, `job_profit.py`, `pages/1_MargenX_Import.py` | Merged (#123). ChatGPT manual review FAIL (answers could survive a file change) → fixed → re-review PASS WITH WARNINGS → final **PASS**. 774 tests. |
| **Excel (.xlsx) and report-style files:** numbers read from the exact stored text, never rounded while reading; title lines skipped; total, heading and footer rows skipped only when proven, everything unclear rejected as possibly missing money; size, unpacked-size and shape limits | `job_intake.py` (`read_file`), `tests/test_file_reading.py` | Merged (#116). Tested on made-up files only. Automated review FAIL on one item (numbered title lines like "Paid 500"); ChatGPT manual review **PASS WITH WARNINGS**, no blockers; the owner accepted that item as a D-005 follow-up. 723 tests. |
| **Negative-sales margin test:** a job whose refunds exceed its sales shows no margin percentage and says why | `tests/test_marginx_ui.py` | Merged (#124), with the 2026-10-24 refresh of this file. |
| **App redesign:** dark top bar (logo, "Pilot session · this laptop only" light, End session), a steps column (Add your reports → Answer a few questions → See your money), and consent and upload cards. The owner asked for software, not a website, with no filler content | `marginx_ui.py`, `pages/1_MargenX_Import.py` | Merged (#125). |
| **"Start MargenX" launcher:** double-click to start pilot mode from the approved tip of `main` on GitHub (it needs the internet). It runs only from its own copy in `~/MargenX-app`, after checking every file byte for byte against the approved commit. It runs git with its program-running features (hooks, file monitors, helpers) switched off, ignores git and Python settings handed to it, and uses only the Mac's own system programs. It trusts the Mac itself; the details and limits are in the script's comments and #126. Also: the End session label never cut off; wording "End session clears the app's data" | `scripts/start_margenx.command` (a copy is on the owner's Desktop) | Merged (#126). Six manual review rounds on the launcher's safety; the last was PASS WITH WARNINGS. 808 tests. |
| **Phone and narrow screens, plus a real upload test:** the "Pilot session" label is never cut off on phones, End session stays in reach, clearer wording. Display and wording only; no figure, rule or clearing step changed. A real browser upload of all 4 made-up file sets matched the sample switch, and End session cleared everything | `marginx_ui.py`, `pages/1_MargenX_Import.py` | Merged (#127). |
| **QuickBooks step 1 (issue #128):** a file that looks like a QuickBooks report is refused with a plain message, so the $405 Cost-of-Goods-Sold-as-sales mistake can't happen. A sales file that mixes in payments or deposits is refused. New QuickBooks line rules are written and tested but **not connected to a reader yet** (a COGS Invoice is never a sale; payments, deposits and unapplied cash are never counted automatically) | `quickbooks_rules.py`, `job_intake.py`, `tests/test_quickbooks_rules.py` | Merged (#129). ChatGPT manual review **PASS WITH WARNINGS**, 0 blockers; its follow-ups are on #128. 847 tests. |

### What the results page shows (#108, updated in #122)
As implemented and tested in #108 and #122 (regression tests in `tests/test_marginx_ui.py`, `tests/test_marginx_insights.py`, `tests/test_marginx_import_page.py`), and reviewed in the ChatGPT manual review round 2. This summary is not itself evidence. The rule behind it: **a number that is incomplete says so, or isn't shown.**
- **Headline cards** (Sales, Left after job costs, Profit margin, Jobs losing money) say which jobs they cover ("From 3 of 7 jobs" / "From all 8 jobs") and disclose sales with no job number and rows that couldn't be read. **Profit margin** uses the same jobs as "Left after job costs":
  - When it counts jobs that need a check, it says it "may change" and also gives the complete jobs' margin.
  - With no figures, or sales of $0 or less, it shows no percentage and says why.
  - The "Jobs that need a check" card was removed in #122; the attention list names those jobs.
- **Jobs losing money** counts only jobs with complete costs. A job that needs a check and shows a loss so far reads "**may have** lost $X", with its real reason.
- **After overhead:** "After $X of costs not tied to any job, these files leave $Y, a N% margin on all sales" appears only when every sale is in the job total and no row was rejected. Otherwise it is withheld, and the page says what's left out. Overhead (rent, fees) is kept apart from costs with no job number.
- **Customers** are a table (sales, left after job costs, margin, "so far" when a check is needed, losses in red), sorted by what they leave you (#122).
- **Biggest customer** finding: compared only against customers with complete figures, and qualified when a bigger customer may be hidden. Break-even is "to cover its job costs (before overhead not assigned to this job)". The usual margin is the share of sales kept across complete jobs (sales-weighted, not an average). Margins are kept and compared as exact fractions, so a near-tie (a job exactly at half the usual margin, a customer exactly 15 points below) is never decided by a cut-off decimal; only shown percentages and "about $X" prices are rounded (margin follow-up from the #118 manual review).
- **Outside web requests:** the page's own styles load no web fonts, and file text can't inject Markdown images or links (`marginx_ui.md_text`, one-line HTML blocks). In one fresh-browser check at `7811bb4` on 2026-10-20, all 134 requests went to localhost. That's a single manual check, not an audit of every path.

### Names that intentionally keep the old spelling
Internal code names (`marginx_ui.py`, `marginx_insights.py`, `marginx_pilot.py`, `MARGINX_PILOT`, branch names), `docs/DECISIONS.md` (history), `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md` (file name), and `command_center/` (it counts past PRs titled "MarginX step N"). **`docs/CHATGPT_REVIEW_INSTRUCTIONS.md` still says "MarginX"**: it's the reviewer's prompt, so changing it is the owner's call.

## What is NOT proven or handled yet
- **No real shop export has ever been run.** Everything is tested on fictional files, and "what owners want" is our assumption until conversations confirm it.
- Known gaps (see `docs/MARGINX_REAL_EXPORT_FOLLOWUPS.md`):
  - the exact QuickBooks/Square layouts. On 2026-10-26 the owner exported three reports from QuickBooks Online's made-up practice company. MargenX read them wrongly (0 of 122 lines from Sales by Customer Detail; $405 of Cost of Goods Sold counted as sales from Profit and Loss Detail). Since #129 those reports are refused. Reading them correctly is the approved plan in issue #128, steps 2–7, which are paused (see below). No real shop's export has been seen.
  - bills without job numbers: handled since #123 by asking the owner (never guessed); untested on real exports
  - labor paid as wages, not per job (would make most jobs "needs a check")
  - sales tax
  - card/processing fees
  - date coverage across files
  - inventory vs. cost of goods sold
  - quoted vs. actual
  - apparel shops that sell products rather than jobs
  - Spanish
- **"Complete" means complete per the imported files** (sales, labor, and materials or outsourced work present, nothing rejected), not reconciled business profit. MargenX can't know about costs that were never recorded.
- The website draft claims things MargenX doesn't do yet (labor hours, quoted vs. actual, card fees, the "change what happened" sliders). Fix them before it goes public. Excel reading now exists (#116), but only on made-up files.
- **Real customer data is prohibited** until step 3b is done and the owner records the real-data decision (**D-008 or later**, since D-007 is the wider target; real data approved for a named pilot shop).

## Next actions, in order
1. **Get the first real shop meeting.** Customer outreach per the 2026-10-22 plan **[unverified]**: Abrey's short calls → meetings with Alex. Owner decision 2026-10-26 (recorded on issue #128): **nothing more is built until after the first real meeting.** Questions worth answering there:
   - QuickBooks Online, QuickBooks Desktop or Excel?
   - Are jobs tracked in it (QuickBooks sub-customers or Projects)?
   - Would the owner download a report?
2. **Then decide how to continue issue #128** (reading QuickBooks reports). Its plan v7 passed a manual review with no blockers, and Alex chose Profit and Loss Detail as the sales source when both reports are uploaded (both recorded on #128). Steps 2–7 are paused.
   - The owner's direction (2026-10-26, from a Claude Code session) **[unverified]** is to **give shops the software** rather than have them send files. Options: an app on their computer, a website, or a "Connect to QuickBooks" button. To be decided after meetings; production deployment and live integrations need separate owner decisions.
3. Small follow-ups (non-blocking):
   - the #129 review's follow-ups, listed on #128 for the step that needs each;
   - optional test additions from the #113 and #115 reviews (see those PRs);
   - **owner decision:** whether to update `docs/CHATGPT_REVIEW_INSTRUCTIONS.md` to the new name (it still says "MarginX" once).
4. Other owner decisions pending:
   - whether to build the Opportunity Radar **evidence store** (issue #1, open), proposed so conversation notes become scored evidence;
   - Abrey logs leads and what owners said in the plan document's "Starter leads" tab **[unverified]**. Whether that later moves into the repository (for example the evidence store) is the owner's call.
5. The real-data decision (D-008 or later), then the first sit-down pilot visit, following `docs/PILOT_VISIT_CHECKLIST.md`. Start MargenX with the Desktop "Start MargenX" launcher. Repeat the real upload-and-delete browser test before it, now with an Excel file too.

## Paused or background
- **AI-team readiness gate** (Suites A/B/C, #11/#69/#35): paused by the owner's choice (focus on MargenX). The run details below are from an earlier snapshot and weren't re-checked on 2026-10-24; #69 is still open. The round-3 Suite A scheduled run `39175749268` (2026-10-18, at `34e43ee`) **failed** and is **not recorded on #69**. Every scheduled run since refuses at "Require reviewed hardening change" (expected; no paid call). A→B→C successes: 0. Unattended agents stay disabled.
- **QuickBooks report reading** (issue #128, steps 2–7): paused by the owner until after the first real shop meeting. Step 1 (#129) is merged.
- **Opportunity Radar:** the scoring foundation is on `main` (`opportunity_radar/`); the evidence store (issue #1) isn't built.
- Draft PRs #16 (old LEDGER website), #39/#62/#63/#64 (trial evidence) and #67/#70 (old readiness drafts) stay unmerged on purpose.
