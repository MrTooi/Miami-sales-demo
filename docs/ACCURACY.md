# How we know MargenX's numbers are right

MargenX's job is to show shop owners true numbers, so its math is checked four ways. Everything
here uses made-up data only.

## 1. One job worked by hand (the demo shop's rush banner)

From `sample_data/marginx/demo_sign_shop_*.csv`, job **J-105, Rush banner (next-day)**, for Bayside
Realty (fictional):

| Step | Where it comes from | Amount |
|---|---|---|
| Sold for | invoice INV-2005 | $600.00 |
| Materials | bill B-510 (rush banner material) | −$340.00 |
| Outsourced work | bill B-511 (after-hours install) | −$280.00 |
| Labor | bill B-512 (overtime print) | −$120.00 |
| **Left after job costs** | $600 − $340 − $280 − $120 | **−$140.00** (a loss) |
| Margin | −$140 ÷ $600 = −23.3% | shown as **−23%** |
| Price to cover its job costs | $340 + $280 + $120 | **$740** |

**The "usual margin" and the suggested price:**
- The usual margin is the share of sales kept across the jobs with complete costs: all of them
  except J-108, which has no labor recorded.
  - Those 7 jobs sold $10,300 and kept $3,120: $1,300 + $480 + $280 + $470 − $140 + $600 + $130.
  - $3,120 ÷ $10,300 = 30.29%, shown as **30%**.
- At that margin, J-105 should have been priced at $740 ÷ (1 − $3,120/$10,300) = $740 × $10,300 ÷ $7,180
  = $1,061.56, shown as **about $1,062**.

**The headline numbers, by hand:**

| Number | Working | Result |
|---|---|---|
| Sales | $2,400 + $850 + $1,200 + $950 + $600 + $1,100 + $3,200 + $700 | **$11,000** |
| Left after job costs | the 8 jobs' figures: $1,300 + $480 + $280 + $470 − $140 + $600 + $130 + $520 | **$3,640** (33% of sales) |
| Jobs losing money | only J-105 is below zero, and it has complete costs | **1 of 7** |
| After overhead | $3,640 − $2,000 rent (bill B-519, no job number) | **$1,640** |
| Bayside Realty | sold $850 + $1,200 + $600 + $3,200 = $5,850; kept $480 + $280 − $140 + $130 = $750 | **13%** |

All of these match what MargenX shows. `tests/test_accuracy.py` checks them on every change.

## 2. A second, independent calculator

`tests/accuracy_shops.py` works out the right answers **without using any MargenX code**:
- in whole cents (integers, never floating-point)
- from MargenX's written rules, not from its code

## 3. Thousands of made-up shops with known answers

The same file makes random shops from a seed. They include:
- several customers, credits and refunds
- labor, materials, outside work, fees and rent
- $0 placeholder lines
- jobs missing sales or costs
- jobs billed to two customers
- rent recorded directly on a job (it counts as that job's cost)
- sales and costs with no job number
- margins that land exactly on a half percent

Each shop is written out as ordinary CSV files and read by MargenX like an upload. Then every job,
customer and headline number, every status ("Complete", "Needs a check", "No figure yet") and, for
complete jobs, the suggested price at the usual margin (as an exact whole-dollar amount) is
compared with the known answer.

- Every change: 400 shops are checked automatically (`tests/test_accuracy.py`).
- On demand: `python scripts/accuracy_check.py 5000`.
  - Result on 2026-10-20, at the commit that last changed this file: **5,000 shops, 53,311 jobs and
    20,202 customers, all matching**, including the screen check. The shops come from fixed seeds,
    so re-running gives the same shops and counts.

## 4. The numbers on the screen

For every one of those shops, the results screen is read back as the HTML MargenX sends to the
browser and compared with the known answers:
- the Sales, Left after job costs and Jobs losing money cards
- every job's amount, margin, status label ("Complete", "Needs a check", "No figure yet") and
  "Sold for" line
- every customer's amount, share and "Needs a check" note
- the note naming customers with no figure, who must not be listed
- the empty states: a dash, never $0, when no job has a figure or none has complete costs (also
  checked on two fixed shops, plus a test that a wrongly shown $0 card or after-overhead total fails)
- the "after overhead" line: shown with the right amount, or withheld when something is left out

This checks what MargenX sends, not how a particular browser draws it. The browser checks are done
by hand (for example, before each pilot visit).

## Proving the checks catch mistakes

`python scripts/accuracy_mutations.py` plants bugs in MargenX on purpose, one at a time and only
in memory, to see whether the checks notice. Each one was caught across many of the first 400 shops:

| Planted mistake | Shops that caught it |
|---|---|
| Shipping counted as materials (wrong "Complete" status) | 276 |
| Fees recorded on a job left out of its costs | 340 |
| Credits left out of total sales | 109 |
| Overhead wrongly taken out of "left after job costs" | 325 |
| Percentages rounded the wrong way at exact halves | 204 |
| Customer names never matched to sales with no job number (so those sales can't stop "Complete") | 43 |

## 5. QuickBooks' Profit and Loss Detail (issue #128, steps 3 and 4)

MargenX doesn't use QuickBooks reports yet: uploads still refuse them. What is checked now is the
reading underneath, before anything is shown to a shop.

**One report worked by hand** (`tests/quickbooks_fixtures.py`, made up, in the layout QuickBooks
Online exported on 2026-10-26):

| Section | Lines | Its total | Counted | Held ("not resolved") | Status |
|---|---|---|---|---|---|
| Income | $900 Invoice, $300 Sales Receipt | $1,200 | $1,200 as sales | $0 | Complete |
| Cost of Goods Sold | $150 "Invoice" (QuickBooks posts the cost of the items sold this way) | $150 | $150 as costs (since step 4), never a sale | $0 | Complete |
| Expenses › Automobile › Fuel | $200.11 and $149.30 Expenses | $349.41 (stored as 349.40999999999997) | $349.41 as costs | $0 | Complete |
| Other Expense | $80 Check | $80 | $0 | $80: you say what it is | Needs a check |

Every total in the file is checked against its own lines to the cent: Gross Profit $1,200 − $150 =
$1,050; Net Ordinary Income $1,050 − $349.41 = $700.59; Net Income $700.59 − $80 = $620.59.
`tests/test_quickbooks_pnl.py` checks all of these.

**Random reports with known answers.** `tests/qbo_pnl_reports.py` makes reports from a seed:
- nested accounts, with and without their own lines;
- the "Cost of Goods Sold" account inside its own section;
- the empty "Other Income" heading;
- money in and out of every type, and negative or $0 lines;
- "Unapplied Cash" accounts;
- totals stored with Excel's float noise.

It works out the right answers in whole cents **without any MargenX code**:
- line counts;
- each section's sum, its sales, its costs and its held amount;
- each section's status.

One report in four has a total a cent off, or a fraction of a cent off; that section, and only that
section, must be held.

Since step 4 the generator also works out, from the written rule for names (S5), each customer's and
each job's sales and job costs, with every cost account answered "job costs". Names include
"Customer:Job", a customer alone, vendors, two ":" and an empty job, which must prove nothing.

What this proves: line counts, section sums and statuses, customer and job sums, and each customer's
sales and costs status, for the layouts and transaction types the generator makes. It doesn't check job
statuses (one report never makes a job Complete) or the owner's answers, which the targeted tests do. It doesn't prove each row's own outcome or other layouts:
`tests/test_quickbooks_pnl.py` and `tests/test_quickbooks_figures.py` hold those targeted cases,
including the plan's own S8 and S9 examples worked by hand.

- Every change: 300 reports (`tests/test_quickbooks_pnl_accuracy.py`).
- On demand: `QBO_PNL_REPORTS=3000 python -m unittest tests.test_quickbooks_pnl_accuracy`.
  - Result on 2026-11-04 (step 4): **3,000 reports, all matching**, sections, customers and jobs.
- Planted mistakes, each caught: a looser float rule (0.02 instead of 0.000001), totals ignored when
  counting, a Deposit counted as a sale, and a sum a cent off on long accounts. Step 4 adds: a vendor
  taken for a customer, the one-report hold on jobs dropped, held lines that never hold customers,
  duplicates accepted without their checks, and customer profit leaving out costs with no job.

**Not proven yet:** combining two reports (step 5), so no job is Complete from one report; whether other
real exports store numbers and dates the way the one seen does.

## What this doesn't prove

- **Real exports.** The made-up shops use one simple CSV layout. Real QuickBooks or Square files,
  odd formats and messy rows are tested separately (`tests/test_job_intake.py`), and real shop
  exports haven't been tried yet.
- **Shared understanding.** The independent calculator follows MargenX's written rules as Claude
  Code understood them. If a rule itself were wrong (for example, what should count as "Complete"),
  both would agree and still be wrong. Shop conversations and the pilot are how we check the rules.
- **Negative costs.** Cost refunds or credits aren't generated: MargenX refuses negative cost lines
  when reading a file (tested in `tests/test_job_intake.py`).
- **Only what MargenX claims.** These checks cover direct job contribution as defined in
  `docs/MVP_SPEC.md`. They don't check business profit, taxes or cash.
