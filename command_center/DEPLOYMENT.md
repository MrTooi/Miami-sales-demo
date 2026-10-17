# Ledger Command Center — Private Deployment Checklist

This checklist applies only to the internal owner Command Center. It is not a Ledger customer deployment.

## Required before going live

- Hosting must require authentication. An obscure URL is not privacy.
- Access should be limited to the owner unless explicitly expanded later.
- Use HTTPS only.
- Store `GITHUB_TOKEN` only in the host's encrypted environment/secrets store.
- The GitHub token must be read-only and scoped only as broadly as needed to read repository metadata and Actions status.
- Never commit a token, password, customer file, financial record, or session secret.
- Keep the dashboard read-only: no merge, deploy, workflow-dispatch, rerun, delete, issue-write, PR-write, or financial-action controls.
- The app must continue to show `UNKNOWN`/`CHECK` when source data cannot be verified.
- Artifact-name presence must remain telemetry only; the dashboard must not replace the authoritative A/B/C readiness validator.

## Pre-launch verification

1. CI is green on the exact Command Center commit being deployed.
2. Independent review has no unresolved false-green or write-path findings.
3. Open the site while signed out and verify access is denied.
4. Sign in as the owner and verify both Command Center and Project Map pages load.
5. Verify the displayed `main` SHA matches GitHub.
6. Verify CI `HEALTHY` only appears when the successful test run is on that exact `main` SHA.
7. Verify the latest Operator status comes only from genuine `event=schedule` runs.
8. Verify API failure/rate-limit behavior becomes `UNKNOWN`/`CHECK`, never green.
9. Verify no customer data appears anywhere in the UI or logs.
10. Verify the 30-second refresh works with the read-only token without exhausting API limits.

## Owner experience

Once deployed, bookmark the private URL. On mobile, the authenticated site can be added to the home screen so it behaves like an app shortcut. A native mobile/desktop wrapper is optional later; the private web app is the first target.

## Rollback

If authentication, evidence semantics, or read-only guarantees fail, take the Command Center offline rather than exposing an inaccurate or writable dashboard. The Ledger product and readiness workflows must continue independently of this internal display.
