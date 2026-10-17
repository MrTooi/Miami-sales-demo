# Ledger Command Center

Internal owner-only operations dashboard for Ledger.

## Purpose

Give the owner one visual place to see:
- current `main` commit and CI health
- A → B → C readiness progress
- genuine schedule-originated Operator activity
- next expected Operator window
- open PRs and readiness/blocker issues
- recent GitHub Actions activity
- whether anything currently needs human attention
- evidence-backed status labels instead of guessed progress

## Safety boundary

This is internal tooling, not customer-facing Ledger product functionality.

The dashboard is intentionally read-only. It does not merge, deploy, delete, mutate financial data, access customer data, or bypass any readiness/commercial/discovery gate.

## Run locally

From the repository root:

```bash
streamlit run command_center/app.py
```

The repository is public, so the basic dashboard can read public GitHub metadata without a token. For higher API limits and richer private deployment behavior, configure a read-only `GITHUB_TOKEN` as an environment variable or Streamlit secret. Never commit a token.

## Deployment target

After the MVP is reviewed and tested, deploy it as a private owner-only web app and bookmark it / add it to the home screen. Hosting should provide authentication; an obscure URL alone is not considered private.

## Status semantics

- `VERIFIED PASS`: supported by the expected final-readiness evidence artifact from a successful schedule-originated run.
- `IN PROGRESS / NEXT`: current suite has not yet produced verified evidence.
- `WAITING`: no qualifying run is visible yet.
- `LOCKED`: a prior suite must pass first.
- `UNKNOWN`: the dashboard could not retrieve enough evidence; it never guesses.
