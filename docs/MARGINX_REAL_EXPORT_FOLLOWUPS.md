# MargenX: follow-ups before real export files

**Status:** open. These items are deferred under D-005. They must be resolved, or each one explicitly accepted by the owner, **before any real customer data is used** (D-003, step 3).

**Source:** the PR #102 manual reviews (final verdict PASS WITH WARNINGS at `dffb13d`) and the automated screening on PR #102, which was still FAIL at `dffb13d`.

## Deferred automated-screening findings (owner reconciliation under D-005)
At `dffb13d`, the automated screening flagged two cost-category labels that can still be imported as ordinary costs:
- **"Inventory - Materials":** an inventory name joined with " - " is not caught by the exact inventory-name checks.
- **"Retained Earnings":** an equity account is accepted as a cost category.

The manual reviewer judged that neither is established as a common job-linked cost record in the invoice/bill layouts this fictional-data step supports, so both are deferred here. **They are not considered safe.** Account-type-aware validation against real QuickBooks metadata (first item below) must cover them.

## Before the real pilot (required)
1. **Account types from real QuickBooks metadata.** Validate account types (income, expense, COGS, asset, liability, equity, bank, credit card) from real QuickBooks exports instead of guessing from label text. This must cover "Inventory - Materials", "Retained Earnings" and other equity accounts.
2. **Source-specific treatment.** Check how each source records revenue, expenses, refunds, credit signs, sales tax and liabilities.
3. **QuickBooks layouts.** Test representative QuickBooks Online and Desktop invoice and bill exports: line amounts vs. document totals, transaction types, account hierarchy, inventory vs. COGS.
4. **Square reports.** Confirm what each field means (gross vs. net sales, discounts, refunds, taxes, processing fees, settlements/payouts), so nothing is double-counted.
5. **Job links.** Confirm that jobs are linked across invoices and bills, and how complete those links are. Use source transaction and line identifiers for duplicate detection instead of exact-row matching.
6. **Report-style exports (Excel and CSV).** Reading Excel and report layouts (title lines, total and heading rows) is built and tested on made-up files only (`tests/test_file_reading.py`). Still to confirm with a real export, such as the QuickBooks Online test drive or a shop's screen:
   - the exact column names and order of "Sales by Customer Detail" and of a costs report
   - whether line rows repeat the customer name, or name it only in a heading row above them. MargenX doesn't copy a heading down onto the lines below it, so if lines leave the customer blank they are rejected with a reason, never guessed.
   - how real exports lay out costs that are tied only to a customer, or to nothing.
7. **Coverage.** Check the dates and sources each export covers, so "Complete" isn't read as "every transaction for the job was supplied".
8. **Pilot data safety.** Complete the D-003 pilot data-safety minimums (security, provenance, retention), then get a separate owner decision before real data is used.
9. **Real uploads.** Test real browser uploads and multi-file sessions.

## Before the pilot (recommended)
- **Fee categories.** Make intake fee types and profit-report categories match. "Bank service charges" and "Transfer fee" are accepted as fees at intake but reported under "Other job costs".

## Before production
- Set limits on aggregate Decimal amounts and add more reconciliation checks.
