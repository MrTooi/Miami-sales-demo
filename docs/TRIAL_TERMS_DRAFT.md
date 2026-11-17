# MargenX free trial: terms and privacy notice (DRAFT, issue #131)

**Status: a draft for Alex and a lawyer. Not legal advice, and not in use.** It follows the plan's topics (lean v1.2, section 7). Alex approves the final text in writing; a lawyer reviewing it once before the first trial is recommended (#131, section 8, item 9). The shop's named person accepts it **before** access is switched on. It replaces the sit-down pilot agreement for the website trial only.

**It can't be used until all of these are true:** the trial-uploads PR is merged and every release check has passed (`docs/TRIAL_RELEASE_CHECKS.md`); Render's written answer on retention is in (plan section 3.4); and the blanks below are filled in. Until then, the trial shows made-up samples only.

**Blanks Alex fills in:** `[PROVIDER]` (Alex, or a company), `[STATE]` (whose law applies), `[SUPPORT CONTACT]` and `[REPLY TIME]` (the support reply time Alex can really keep: #131, section 8, item 10), `[INCIDENT NOTICE TIME]`, `[SHOP]`, `[NAMED PERSON]`, `[START DATE]`, `[CLOSEOUT DATE AND TIME, MIAMI]`.

---

## MargenX free trial terms

**Between** `[PROVIDER]` ("MargenX", "we") **and** `[SHOP]`, through `[NAMED PERSON]` ("you").

**1. What the trial is.** A free, private trial of MargenX for one shop and one named person, by invitation. It runs for 14 calendar dates, from `[START DATE]` (the day access is switched on) to the closeout at `[CLOSEOUT DATE AND TIME, MIAMI]`. Only your exact work email is invited. Please don't share your login or let anyone else use it.

**2. What MargenX shows.** For the file you upload, MargenX shows **sales minus direct job costs**, by job and by customer, exact to the cent. **It is not net profit**: it leaves out overhead, taxes and anything not in your file. Every figure says whether it is **Complete** or **Needs a check**. "Needs a check" means MargenX couldn't prove the figure from your file, and says why. **Complete means MargenX's required checks and your confirmations are satisfied. It doesn't guarantee that nothing was left out of, or recorded wrongly in, QuickBooks** (section 3). **Many figures may show Needs a check, even when you follow the export steps exactly.** That's MargenX refusing to guess, not an error.

**3. What MargenX can and can't check.** MargenX reads one supported file: QuickBooks Online's **Profit and Loss Detail**, exported to Excel on the accrual basis, plus optionally **Sales by Customer Detail** for the same dates (the guide gives the steps). Other files are refused with a plain message. **MargenX can only check what the file itself shows.** QuickBooks can filter a report in ways it doesn't print in the file, for example leaving out an account or a customer. MargenX can't see that, so please follow the export steps exactly. **So MargenX asks you:** after its other questions, it lists the cost accounts it found in your file, with their totals, and asks you to confirm that the file includes your whole business's income and costs for those dates, with no filters excluding accounts or transactions. Until you answer "Yes, I checked", every figure shows Needs a check. **You agree that MargenX relies on that confirmation,** as it says with your results: "MargenX calculates figures from your uploaded reports and your answers. QuickBooks exports may not reveal filters that excluded accounts or transactions. We therefore ask you to check the export settings and confirm its coverage. Complete means our required checks and confirmations are satisfied; it does not guarantee that nothing was omitted or incorrectly recorded in QuickBooks. If you are unsure, choose Not sure." The check we did together at our meeting covered only the export we saw that day.

**4. What to leave out.** Upload only the supported report. Don't upload, type or send us bank or card details, tax ID numbers, or individual payroll records. **You confirm you're allowed to share this report with us** for this trial.

**5. Where your file goes.** Your file travels over an encrypted connection through **Cloudflare** (which runs the login and the connection) to a server run by **Render** (which hosts MargenX's copy for your shop). Both act for us as service providers. MargenX reads your file **in memory only**: it doesn't save it to a disk or a database, keeps no backups, and doesn't put your file's contents in its logs. Your copy of MargenX is yours alone during the trial, and is stopped at the end. **What we can't guarantee:** Cloudflare and Render keep their own records of logins and connections (for example your email, times and internet address), under their own terms; and we can't control what your own browser, computer or screenshots keep.

**6. Logging out.** The Log out button ends your MargenX session straight away, once MargenX has confirmed your login. If it can't confirm it in time (for example while Cloudflare's login service is slow), it says "Not allowed." and nothing is logged out: press Log out again, and if it keeps failing, close the browser and tell us. The login itself may take a short moment to end everywhere (Cloudflare documents a short delay). Closing the tab doesn't log you out.

**7. The closeout, and ending early.** At the closeout, we stop your copy of MargenX. Stopping cuts the server off: any open tab loses its connection, any upload in progress is ended, and everything held in memory is cleared. Figures already on your screen may stay visible there, and anything you saved or screenshotted stays with you. Either of us may end the trial earlier, at any time, by telling the other; we then stop your copy the same way. Nothing brings an ended trial back.

**8. If something goes wrong.** If we learn of a problem that may have exposed your file or results, we stop your copy at once and tell you within `[INCIDENT NOTICE TIME]`, with what we know. If you notice anything odd, contact us at `[SUPPORT CONTACT]`. We aim to reply within `[REPLY TIME]`. **Please never email us a financial file**: we'll help without it.

**9. Free, with no automatic charge.** The trial is free. We don't ask for payment details, and nothing turns into a paid plan by itself.

**10. No warranty.** MargenX is a trial of software still being built. It's provided "as is". Please check important figures against your own records before relying on them for decisions.

**11. Liability.** `[LAWYER TO DRAFT: limitation of liability suitable for a free trial, under [STATE] law.]`

**12. Accepting.** By accepting, you confirm that you are `[NAMED PERSON]`, that you can accept these terms for `[SHOP]`, and that you're allowed to share the report described in section 3.

---

## Notes for Alex (not part of the terms)
- **Several promises above are still conditional.** They follow the plan, but each must be shown true before the terms are used:
  - section 5's "in memory only", "no backups" and "not in logs": the uploads PR's cleanup and marker tests (release checks 2 and 6), and Render's written answer on what it keeps (plan section 3.4);
  - section 7's stop: the release run's check 5 on Render (the stop-now's timing and the Shell after Suspend), and the slow-upload part in the uploads PR.

  What already matches the plan: one supported format, refused otherwise (section 3.1); the simple logout promise (D-009, Alex 2026-11-04); the stop procedure's order (section 3.5). Section 2's "Needs a check" wording follows the review's warning that shops may see mostly Needs a check.
- **The money decision is settled and built** (D-010; PR #148 and #149, merged Nov 17): a filter can't be seen in the file, so every figure needs the owner's coverage confirmation before it can be Complete. Sections 2 and 3 describe that, and quote the reliance wording the results show (`quickbooks_figures.RELIANCE`), as D-010 requires. If that wording changes in the app, change it here too.
- **Section 5 must match Render's written answer** (retention, builds) and the privacy wording on margenx.org.
- **No figures, results, customers or savings are promised.**
