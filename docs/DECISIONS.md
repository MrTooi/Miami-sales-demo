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
