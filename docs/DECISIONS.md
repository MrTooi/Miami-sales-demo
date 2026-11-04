# Decision Log

Lightweight ADR-style log. Append new entries at the bottom; do not rewrite accepted entries (supersede them instead).

## Template

```
### D-NNN — Title
- Date:
- Status: Proposed | Accepted | Superseded by D-NNN
- Decided by:
- Context:
- Decision:
- Consequences / risks:
- Evidence / links (issues, PRs):
```

## Decisions

### D-001 — Transfer Ledger technical leadership to Claude Code
- Date: 2026-10-17
- Status: Accepted (takes effect when the PR implementing Issue #88 is approved and merged by the human owner)
- Decided by: Human owner (Issue #88)
- Context: The operating model needs a repo-local, GitHub-visible definition so that Claude Code and ChatGPT can work from shared state rather than private conversation history.
- Decision: Claude Code is the primary technical lead for authorized engineering work. ChatGPT is product/strategy/architecture/independent-review support. The human owner keeps final authority. Claude is never the sole reviewer of its own high-risk changes. Claude Code runs only when triggered by tasks, events, or schedules.
- Consequences / risks: Documentation and instructions only. Autonomy is limited to what is authorized; see `docs/LEADERSHIP_MODEL.md`.
- Evidence / links: Issue #88, Issue #89; `CLAUDE.md`; `docs/LEADERSHIP_MODEL.md`.

### D-002 — Readiness gates unchanged; product stays paused
- Date: 2026-10-17
- Status: Accepted; its product-pause clause is superseded by D-003
- Decided by: Human owner (Issue #88)
- Context: Leadership transfer must not alter readiness semantics.
- Decision: Readiness gates, rubrics, scorer thresholds, model configuration, and workflow logic are unchanged. Product implementation remains PAUSED until Issue #11 / Issue #69 readiness is satisfied and the human owner explicitly approves resuming (to be logged as a new decision).
- Consequences / risks: Only these proceed: readiness hardening and readiness-infrastructure repair (including audit remediation), owner observability, demo reliability without product/financial logic changes, governance/documentation, and work the owner explicitly assigns. Every merge needs explicit owner approval. The resume decision must name its authorized scope.
- Evidence / links: Issue #88, Issue #11, Issue #69.

### D-003 — Build Ledger now under supervision; A/B/C gates unattended autonomy only
- Date: 2026-10-17
- Status: Accepted
- Decided by: Human owner (MrTooi), who replied "approved: decouple" in a Claude Code session on 2026-10-17 after reviewing the trade-offs. This PR records it; merging it needs the owner's explicit approval as usual.
- Context: Product code had not changed since 2026-10-12, while roughly 9,500 lines went into AI-team readiness infrastructure. Suite A failed twice (12/18, 13/18) with 0 critical safety violations, mainly on role and reviewer selection. Supervised building with independent review and owner-approved merges already works: the workbench trials #25–#28 and PRs #80, #90 and #91.
- Decision:
  1. **Product work resumes in supervised mode.** Claude Code builds through the `AGENTS.md` roles. Every change goes through branch → tests → CI → independent review (ChatGPT or owner) → explicit owner merge approval.
  2. **Authorized scope:** the Ledger pilot MVP for one target customer type. The default is small print/service shops and job profitability. Partner evidence can trigger a *proposed* pivot, but changing the target customer type or scope needs explicit owner confirmation in a new decision. It covers:
     - (a) data import (CSV first, then QuickBooks-style exports) with a "what's missing" report;
     - (b) exact profit by job and by customer, with incomplete data flagged;
     - (c) a "where you're losing money" report;
     - (d) a short weekly owner summary;
     - (e) the pilot data-safety minimums from `LAUNCH_RISK_REGISTER.md`.

     Supporting Opportunity Radar evidence intake is in scope only when the owner assigns it.
  3. **Still not authorized without a separate owner decision:** live financial/provider integrations with real credentials, production deployment, real customer data before the pilot safety minimums are merged and reviewed, pricing/launch claims, and unattended agent execution.
  4. **The A/B/C readiness gate (#11/#69) and the Issue #35 gate now control unattended/autonomous agent execution only.** They remain strict and unchanged: same suites, thresholds, evidence rules and retry barriers. They continue in the background. Real-work failures feed AI-team hardening.
  5. **Real-product rule.** Every task must (a) move a real business closer to using Ledger on its own data, (b) fix something that would break or mislead a customer, or (c) be the minimum needed for quality/safety. Otherwise it isn't done. Each week Claude reports what a business can now do that it couldn't before.
- Consequences / risks: Faster progress to a real pilot, with the same review safeguards. These approvals are a human process, not machine-enforced (branch protection is off), so the owner enforces them manually. Merging the pilot safety minimums is **not** by itself permission to use real customer data: that needs the binding security/privacy requirements, the pilot-readiness criteria (#36, #74/#75 where applicable) and an explicit owner decision. Real customer files never go into the repository. Owner review time is the bottleneck, and the owner accepted that. Readiness for unattended agents may take longer. All finance, security and evidence invariants in `AGENTS.md` still apply in full.
- Evidence / links: Issue #11, Issue #69, Issue #92 (weekly checklist), PRs #80/#90/#91, `docs/CURRENT_STATE.md`.

### D-004 — Automatic independent ChatGPT review on pull requests
- Date: 2026-10-18
- Status: Accepted (takes effect when the PR adding the workflow is merged with the owner's approval)
- Decided by: Human owner (MrTooi), who wrote "arrroved auto chatgpt review" in a Claude Code session on 2026-10-18. This also authorizes the `.github/workflows/chatgpt-pr-review.yml` change. Recorded on #92.
- Context: The owner was pasting every review prompt into ChatGPT by hand, which is slow and error-prone.
- Decision:
  1. Every non-draft pull request from this repository gets an automatic ChatGPT review. Claude Code may also trigger one by PR number.
  2. **How it runs:**
     - The workflow runs base-branch code only.
     - The PR's code is never checked out or executed.
     - The diff is sent as untrusted data, with fixed instructions read from `main` (`docs/CHATGPT_REVIEW_INSTRUCTIONS.md`).
     - The model's verdict is posted to the PR verbatim, with the reviewed commit SHA.
  3. **When a review qualifies:** the workflow, not the model, decides. Everything else is posted as **REVIEW INCOMPLETE** and does not count.
     - The answer has exactly one valid verdict and every required section.
     - It does not contradict itself; for example, a PASS cannot list required changes.
     - It covers the whole diff, so a truncated diff can only FAIL.
     - It is for the PR's current head commit.

     Claude cannot edit or filter the answer. A FAIL or a required change must be fixed and re-reviewed.
  4. **What a qualifying review counts for:**
     - **Low-risk changes** (docs, copy, UI wording, tests-only, tooling outside the high-risk areas): it counts as the ChatGPT independent review required by `CLAUDE.md`.
     - **High-risk changes** (finance logic, security/auth/tenant boundaries, readiness gates/evals/workflows, deployment, customer data): it is **screening only**. A separate manual independent review (ChatGPT with full repository and CI access, or the owner) is still required.
  5. **Not changed:**
     - Merging still needs the owner's explicit approval for that PR.
     - The owner may still ask for a manual ChatGPT or owner review at any time.
- Consequences / risks:
  - Each review costs a small amount of OpenAI usage on the existing `OPENAI_API_KEY`.
  - The owner chooses the model in the repository variable `MARGINX_REVIEW_MODEL`. The workflow fails closed until it is set.
  - Changing the reviewer instructions needs its own owner-approved PR.
  - The diff can carry prompt-injection text. It is labeled as data, but the owner remains the final check.
  - Diffs over 150,000 characters are truncated and cannot produce a qualifying PASS.
  - Requests are sent with `store: false`.
  - A diff or description that looks like it contains a credential is never sent.
- Evidence / links: Issue #92.

### D-005 — Stopping rule for manual reviews of MarginX import labels while data is fictional-only
- Date: 2026-10-20
- Status: Accepted (in force once this record is merged with the owner's approval)
- Decided by: Human owner (MrTooi), who chose "b" in a Claude Code session on 2026-10-20, after about 15 manual review rounds on PR #102. Each round found one narrower spreadsheet-label variant.
- Context:
  - MarginX reads CSV exports with free-text labels (account names, transaction types, categories). The set of possible labels has no end, so a careful reviewer can always find another variant.
  - Every uncertain case already fails closed: the row is rejected with a reason, and affected jobs and customers are shown as Provisional, never as a confident Complete figure.
  - All data is fictional until the pilot data-safety minimums are merged and the owner approves real data (D-003). The real QuickBooks/Square export layouts are not known yet.
- Decision:
  1. For MarginX import and classification PRs, while data is fictional-only, the manual independent review gives PASS or PASS WITH WARNINGS unless it finds a defect that can show a wrong figure as Complete for a **common, realistic export layout**.
  2. Narrower label variants are listed as "Follow-ups for real pilot files". They are not merge blockers.
  3. Before any real data is used, those follow-ups are resolved by supporting the shops' actual export layouts explicitly. A layout that isn't supported is shown as unsupported or Provisional, never guessed.
- Not changed:
  - D-004 itself: the automatic review still runs, and high-risk changes still need a separate manual review.
  - Merging still needs the owner's explicit approval for each PR.
  - Every finance, security and evidence rule in `AGENTS.md`.
  - Real customer data still needs step 3 (pilot data-safety minimums) and a separate owner decision.
- Consequences / risks:
  - Faster merges for supervised, fictional-data steps.
  - Some label variants stay unhandled until real exports are tested. This is acceptable only because uncertain rows fail closed and no real data is used.
  - The follow-up list must be carried into real-export testing, not forgotten.
- Evidence / links: PR #102 manual review comments; PR #100.

### D-006 — Public demo link: a static page of the made-up demo shop
- Date: 2026-10-20
- Status: Accepted (in force once the PR adding `scripts/build_demo_page.py` is merged with the owner's approval)
- Decided by: Human owner (MrTooi), in a Claude Code session on 2026-10-20. The owner first chose "b just a link we can send to abrey and he can open" (a demo-only website link). After the ChatGPT manual review of PR #112 showed that a hosted Streamlit app always exposes a file-upload endpoint, the owner chose "a", a static demo page with no server.
- Context: Abrey talks to Miami shop owners and needs something real to show. MargenX ran only on the owner's laptop.
- Decision:
  1. The public demo is one static HTML page of the made-up demo sign shop, built by `scripts/build_demo_page.py` from the real MargenX code. It has no server, script, form or upload path, and says plainly that every name and number is invented.
  2. It is published as a claude.ai artifact. The owner shares it from the Share menu. Claude Code never changes sharing or deploys.
  3. No real shop data, sign-up forms, analytics, scripts or visitor-data collection on it without a new owner decision.
- Not changed:
  - Real customer data still needs step 3b and a separate owner decision for a named pilot shop (D-007 or later), and is used only in the sit-down pilot on the team laptop.
  - No hosted Streamlit app is published (PR #112 was closed).
  - Merging still needs the owner's explicit approval for each PR.
- Consequences / risks:
  - Anyone the owner shares the link with sees the made-up demo. Acceptable: it holds no real data and has no input of any kind.
  - The page doesn't update itself: after screen or sample changes, rebuild and republish (`docs/DEMO_LINK.md`).
- Evidence / links: PR #112 (closed) and its ChatGPT manual review; `tests/test_demo_page.py`; `docs/DEMO_LINK.md`.

### D-007 — MargenX is for job-based small businesses, not only print shops
- Date: 2026-10-22 (confirmed for this record on 2026-10-24)
- Status: Accepted (in force once the PR adding this entry is merged with the owner's approval)
- Decided by: Human owner (MrTooi), in a Claude Code session on 2026-10-22: "our product isn't just for print shops we shouldn't try to make a master product for everyone but we can do more". The owner confirmed this wording with "yes, record it" on 2026-10-24. The manual review of PR #122 asked for the record, because D-003 requires a new decision to change the target customer type.
- Context: Walk-in visits to print shops didn't lead to conversations, and the customer plan was redone on 2026-10-22. MargenX's math works the same for any business that bills by job and has job costs.
- Decision:
  1. The pilot target widens from small print/service shops to job-based small businesses:
     - print, sign and apparel shops
     - trade contractors (remodeling, flooring and similar)
     - custom makers and installers (cabinets, metal work and similar)
  2. It isn't a product for every business. (The 2026-10-22 plan lists businesses that only sell time, such as cleaning or consulting, as "not for now", because MargenX needs labor and materials or outsourced work on a job to call it complete.)
  3. The authorized scope of D-003 (a) to (e) is otherwise unchanged.
- Not changed:
  - Real customer data still needs step 3b and a separate owner decision for a named pilot shop, used only in the sit-down pilot on the team laptop.
  - Pricing and launch claims, live integrations, production deployment and unattended agents still need their own owner decisions.
  - Merging still needs the owner's explicit approval for each PR.
- Consequences / risks:
  - Demos and slides are made per business type, with made-up data only (PR #122).
  - Owners in the new groups may record costs differently, for example receipts with no job number. That is handled by asking the owner, never by guessing (PR #123).
  - A wider target can blur focus. The plan's scorecard (Nov 13) decides which groups to keep.
- Evidence / links: PR #122 and its manual review; PR #123; the 2026-10-22 customer plan (shared with Abrey as a claude.ai document, not in this repository).

### D-008 — Real shop data in the lean website trial, one approved shop at a time
- Date: 2026-11-04
- Status: Accepted (in force once the PR adding this entry is merged with the owner's approval). **It allows no real data by itself:** for each shop, real data starts only when every condition in item 2 holds.
- Decided by: Human owner (MrTooi), in a Claude Code session on 2026-11-04. Asked whether a shop may upload its own report to its private copy after the checks, its signed terms and his yes for that shop, he answered: "yes of course they would need to use their real files". Recorded on issue #131.
- Context:
  - D-003 requires an owner decision before any real customer data is used. Earlier records reserved "D-008 or later" for that.
  - Issue #131's lean v1.2 plan (manual review PASS WITH WARNINGS, 2026-11-04) is a two-week trial on a private MargenX website: one shop at a time, one named person, the shop's own running copy, and one supported export (QuickBooks Profit and Loss Detail, read by the #128 work).
- Decision:
  1. **Scope.** A named shop may upload **its own export in the supported profile** to **its own private MargenX copy** in the website trial of #131. Only that shop's one named person, who signed its trial terms, may upload.
     - **The supported profile** is one exact QuickBooks Online Profit and Loss Detail export: report, file type, accrual basis, title, columns, header, filters shown, footer, and how "Customer:Job" appears. **It is written down in the repository before PR B, by the #128 work**, together with which coverage-affecting settings can be verified from the file (lean v1.2, section 3.1). Coverage that can't be established is refused or marked Needs a check, never Complete.
     - **Until #128's Profit and Loss Detail reading is merged, a trial copy accepts only MargenX's made-up samples.**
     - **Eligibility versus each upload:** the invite and the signed terms make a shop eligible. **Every upload still needs server-side consent**, tied to the authenticated person and their current app session, **before the file body is accepted** (lean v1.2, sections 3.3 and 6).
  2. **Conditions for each shop, in this order** (lean v1.2, sections 3.1 and 3.5). The full sequence is in D-009, item 2.
     - **Before that shop's copy is started:**
       - **the fit check passed.** The owner runs the export on their own computer, following the recipe, and Alex checks it **on their screen**:
         - the report and settings match the written profile;
         - sales and job-cost lines carry the customer and job;
         - **the job-cost categories the shop records (labor, materials, outsourced work) appear in it.**

         No file is sent or copied; Alex doesn't photograph, write down or keep any names or figures; only "fit" or "not fit" is recorded privately. **A shop that doesn't fit isn't invited.**
       - its named person accepted the trial terms, whose final text Alex approved in writing;
       - the provider retention evidence (lean v1.2, section 3.4) is complete for the exact host and data path;
       - the six release checks passed on the operator-only baseline;
       - **Alex's explicit yes for that shop**, recorded on issue #131 as "shop A", "shop B" and so on, never by name.
     - **After the copy is started and before the invite is added:** the copy is verified while the shop is still blocked, and the closeout is recorded (D-009, item 2).
     - **The invite is added last.**
  3. **What may be uploaded:** the shop's own export in the supported profile only. Bank and card details, tax IDs and individual payroll records are left out. The named person confirms they are allowed to share the export. MargenX refuses files outside the profile.
  4. **Ending:** at the closeout, or earlier, the trial ends with the stop procedure (D-009). A closed trial stays closed.
- Not changed:
  - Every money-safety rule in `AGENTS.md`, including **Needs a check**: a file that can't prove its coverage never yields a Complete total (lean v1.2, section 3.1). PR B keeps the lean v1.2 review's follow-ups: an unknown-scope test that includes the overall total, and a guide that sets expectations if valid exports produce mostly Needs a check.
  - This covers the website trial only. The sit-down pilot on the team laptop still needs its own owner decision for a named shop.
  - D-004 and D-005; merging still needs the owner's explicit approval for each PR.
- Consequences / risks:
  - The first real financial files would be handled by MargenX, Cloudflare and the host. The retention evidence and the release checks are the safeguards, and missing evidence keeps real uploads off.
  - Per-shop records (names, emails, closeout) are kept privately, not in this public repository.
- Evidence / links: issue #131 (lean v1.2 and its reviews; the owner's answers of 2026-11-04); research `docs/research/TRIAL_HOSTING_AND_LOGIN.md` (#132); #128 and #129.

### D-009 — A private, invite-only MargenX website for the trial: first an operator-only test copy, then one shop's copy at a time
- Date: 2026-11-04 (building it was decided on 2026-11-02)
- Status: Accepted (in force once the PR adding this entry is merged with the owner's approval). Part 1 applies from then on, once item 1's prerequisites hold. Part 2 applies to each shop only in the order of item 2, under D-008.
- Decided by: Human owner (MrTooi), in Claude Code sessions, all recorded on issue #131:
  - 2026-10-26: a private website with a login, rather than an installed app;
  - 2026-11-02: start building now; Cloudflare Access on the free plan; the existing domain margenx.org;
  - 2026-11-04: the smaller "lean v1" plan; the online test copy ("Yes, test copy OK"); the simple logout promise ("simple is fine"); Abrey as the closeout backup ("abrey will do it").
- Context: this is a production deployment of MargenX, which needs an owner decision (`CLAUDE.md`, D-003). Lean v1.2 on #131 passed its manual review on 2026-11-04.
- Decision:
  1. **Part 1, the operator-only test copy.** MargenX may run online behind Cloudflare Access (emailed one-time code, exact invited email), with **only Alex invited** and **made-up files only**. The server has no public address (a tunnel), and no shop can reach it. It's used to build and test PR A and to run PR B's release checks.
     - **Prerequisite before any copy goes online, this one included:** two-step login (MFA) is on for all four administrator accounts: Cloudflare, the host, Porkbun and GitHub. Alex's approval of this, and who switches it on, are still open on #131.
  2. **Part 2, one shop's copy at a time.** Up to three trials in a row, never overlapping. For each shop, in this order (lean v1.2, section 3.5):
     1. **Before starting the copy:** every D-008 "before" condition holds, including **Alex's explicit yes for that shop**.
     2. **Start the shop's copy** from the approved version, **with no invite**, so the shop is blocked.
     3. **Verify it while blocked:**
        - it matches the operator-only baseline (build and settings); any difference re-runs the release checks it could affect, and a changed host or data path also needs retention evidence for that path;
        - an uninvited email is refused, and **the stop control works on that copy**;
        - **restart it, still blocked**, and confirm it came back with the approved build, settings and access restrictions. If a scheduled stop is ever used, it must target that exact copy.
     4. **Record privately:** the Miami closeout date and time, the responsible person and the authorised backup.
     5. **Only then add the single invite**, and tell the shop its trial dates.
  3. **Ending a trial:** one stop procedure for the closeout, an early end and an emergency: stop that shop's copy first, then remove its invite, revoke its Access sessions, and verify the cutoff. Removing an invite without stopping the copy never counts as ending a trial. Nothing restarts a stopped copy by itself.
  4. **Closeout cover:** Abrey is the named backup. Before any trial opens, he has the short stop checklist and the access he needs, with two-step login.
  5. **The logout promise is the simple one,** as recorded on #131: Log out ends the MargenX session; the Cloudflare login may take a short moment to end everywhere. There is no instant-everywhere promise.
  6. **Not allowed without a new decision:**
     - overlapping trials, several users per shop, invitations by anyone but Alex, or an automatically enforced deadline (these return to the fuller plan v7);
     - a public sign-up;
     - storing files or results;
     - paid plans or pricing claims.
- Not changed:
  - **No purchase** (server, domain, anything else) before Alex approves a budget.
  - The hosting provider is chosen by Alex before the deployment. Only a provider whose retention evidence is complete may serve real files (D-008).
  - The move of margenx.org's DNS to Cloudflare needs Alex's approval and Abrey's agreement at the time, with a separate small domain as the fallback.
  - Automatic deploys stay off during a trial. Merging still needs the owner's explicit approval for each PR, and deployment-related PRs get a manual review (D-004).
- Consequences / risks:
  - We become responsible for an online service: its access settings, its providers' data handling, and stopping it on time.
  - Two-step login on the four administrator accounts is a prerequisite (item 1), not just advice.
  - Running costs start once Alex approves a budget.
- Evidence / links: issue #131 (lean v1.2, its reviews, and the owner's decisions of 2026-10-26, 2026-11-02 and 2026-11-04); research `docs/research/TRIAL_HOSTING_AND_LOGIN.md` (#132).
