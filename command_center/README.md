# Ledger Command Center

Internal owner-only operations dashboard for Ledger.

## Purpose

Give the owner one visual place to see:
- current `main` commit and CI health
- A → B → C readiness activity without self-certifying the gate
- genuine schedule-originated Operator activity
- next expected Operator window plus late/missed-run visibility
- open PRs and readiness/blocker issues
- recent GitHub Actions activity
- whether anything currently needs human attention
- evidence-backed status labels instead of guessed progress
- a live Project Map for the major Ledger gates and workstreams

## Pages

### Command Center
The main screen auto-refreshes every 30 seconds and shows readiness telemetry, scheduler timing, CI, work in progress, human-attention items, recent system activity, and guardrails.

### Project Map
The Project Map reads the current GitHub state for the main readiness, commercial, discovery, Command Center, and demo issues. It also shows scheduler health with a delivery-grace window, current PRs, and direct links to schedule runs that contain candidate readiness evidence artifacts.

Issue state is displayed as repository state (`OPEN`, `CLOSED`, or `UNKNOWN`) rather than an invented completion percentage.

## Safety boundary

This is internal tooling, not customer-facing Ledger product functionality.

The dashboard is intentionally read-only. It does not merge, deploy, delete, mutate financial data, access customer data, trigger or rerun workflows, or bypass any readiness/commercial/discovery gate.

The dashboard does **not** decide that Suite A, B, or C passed merely because an artifact exists. Artifact-name presence is telemetry only. The authoritative readiness workflow remains responsible for validating suite order, metadata, hashes, scores, provenance, and the final technical gate.

## Run locally

From the repository root:

```bash
streamlit run command_center/app.py
```

The repository is public, so the basic dashboard can read public GitHub metadata without a token. The 30-second live-refresh mode should use a read-only `GITHUB_TOKEN` as an environment variable or Streamlit secret so normal unauthenticated API limits do not make the view unreliable. Never commit a token.

## Deployment target

After the MVP is reviewed and tested, deploy it as a private owner-only web app and bookmark it / add it to the home screen. Hosting should provide authentication; an obscure URL alone is not considered private.

## Status semantics

- `HEALTHY`: only used when the displayed check is verified against its stated source, such as successful CI on the exact current `main` SHA.
- `VALIDATION PENDING`: candidate readiness evidence exists, but the Command Center does not claim an A/B/C pass from artifact presence.
- `EVIDENCE PRESENT — UNVERIFIED HERE`: a genuine schedule-originated run has the expected non-expired artifact name, but authoritative readiness validation still owns pass/fail.
- `WAITING`: no qualifying schedule event is visible yet, or a schedule slot is still inside its delivery-grace window.
- `LATE / CHECK`: a schedule slot is past its delivery-grace window and no genuine Operator schedule event is visible.
- `LOCKED`: a prior gate or explicit approval still prevents progression.
- `UNKNOWN`: the dashboard could not retrieve enough evidence; it never guesses.
