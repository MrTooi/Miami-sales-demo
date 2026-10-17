# CLAUDE.md — Claude Code session-start protocol

You are working in the LEDGER / Opportunity Radar repository. You have no memory of earlier sessions or of ChatGPT conversations. GitHub is the shared handoff surface with ChatGPT and the human owner.

This file adds a startup protocol. It does **not** expand your authority. `AGENTS.md` and `.github/copilot-instructions.md` remain the binding policy and win on any conflict.

## At the start of every session

1. Read, in order:
   - `AGENTS.md` and `.github/copilot-instructions.md`
   - `docs/CONTEXT_INDEX.md` (what controls what)
   - `docs/PROJECT_CONTEXT.md` (durable principles and invariants)
   - `docs/CURRENT_STATE.md` (dated snapshot)
   - `docs/LEADERSHIP_MODEL.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md` — **if present** (Issue #88 work; they were not on `main` as of 2026-10-17)
   - `PROJECT_BRIEF.md`, `LAUNCH_RISK_REGISTER.md` and `opportunity_radar/README.md` when the task touches them
2. **Then inspect live GitHub before acting**: the triggering issue/PR and its comments, open issues and PRs, CI status on `main` and on the relevant branch, and the current contents of `main`.
3. Treat `docs/CURRENT_STATE.md` as stale-able. It is never more authoritative than live GitHub or `main`. If they disagree, trust GitHub/`main`, say so in your handoff, and propose a docs-only refresh.
4. Work only on what the owner explicitly asked for in the current issue/comment. Product implementation is paused until the readiness gates pass and the owner approves resuming (see `docs/CURRENT_STATE.md`, verify live).

## Standing rules (summary; full text in AGENTS.md)

- Never weaken readiness gates, prompts, rubrics, scorer thresholds, model config, blind/judge separation, evidence standards, permissions, financial integrity, tenant/security boundaries, commercial/discovery gates, or human-approval rules.
- Money uses exact `Decimal`. Payouts/deposits are not revenue. Withhold profit when expenses are incomplete.
- Never invent evidence, customers, savings, ROI, or integrations. Label demo data as fictional.
- No secrets or real customer/bank data anywhere in the repo.
- Branch + PR for meaningful changes. Never push to `main`, merge, or deploy. Human approval is required for high-risk work.
- Do not edit `.github/workflows/`, permissions, or secrets unless the owner explicitly authorizes it.
- If a requirement is ambiguous and money, security, privacy, permissions, deletion, or customer trust is affected, stop and ask rather than guess.
- Do not cite a test, review, or tool action that did not actually happen.

## Handoff after substantial work

Leave a truthful note on the issue/PR covering: outcome, files changed, assumptions, tests/checks actually run, limitations and unknowns, security/data-integrity implications, blockers, and the next owner/action. Mark what you could not verify. If you learned that `docs/CURRENT_STATE.md` is stale, say so.

## Commands

- Tests: `python -m unittest discover -s tests -v` (CI definition: `.github/workflows/tests.yml`)
- Demo app: `streamlit run app.py` (fictional data only)
