# MargenX sample files (fictional)

Every business, person and amount in these files is **made up**, and they contain deliberate problems so the "what's missing" report has something to show:

- **Invoices:** a missing job number, a mixed date format, an exact duplicate row, a missing customer, an amount with 3 decimals, a credit line, and an invoice with two lines.
- **Costs:** costs not linked to a job, a missing cost type, a negative cost, a formula-like memo (shown as text, never run), and no labor costs.

**Demo businesses** (`demo_*`), clean examples to show owners, one per kind of business MargenX is for: a sign shop, a remodeling contractor and a cabinet and metal shop. Each has nothing to answer, one job that lost money, a big customer who barely makes money, one job missing labor, and rent as overhead not tied to a job. `tests/test_demo_businesses.py` checks their figures.

Never put real customer files in this repository.
