# The website trial: setup, operator-only test copy and stop procedure (PR A2, issue #131)

**Status:** this is the recipe. **Nothing is deployed, bought or switched on by this document or its PR.** Trial uploads are off in the code (PR #137): a copy shows MargenX's made-up samples only, until the PR that switches uploads on.

**What the operator-only test copy is (D-009, part 1):** MargenX online behind Cloudflare Access, with **only Alex invited** (his exact email) and **made-up files only**. No shop can reach it. **What a shop's copy needs:** D-009 part 2 and D-008, in their order, with the invite added last. This document doesn't cover shop copies beyond the stop procedure.

Sources: the plan (#131, lean v1.2), the hosting research (`docs/research/TRIAL_HOSTING_AND_LOGIN.md`), D-008 and D-009 (`docs/DECISIONS.md`), and the in-app checks (`trial_access.py`, PR #137).

## 0. Before anything goes online (prerequisites, all recorded on #131)
1. **Two-step login (MFA)** is on for all four administrator accounts: Cloudflare, the host, Porkbun and GitHub (D-009, item 1).
2. **Alex has approved a budget.** Nothing is bought before that (D-009).
3. **Alex has chosen the host,** recorded on #131 (D-009: "chosen by Alex before the deployment"). The steps below are for **Render**, the research's first choice. A different host needs its own steps, reviewed first.
4. **The domain:** Alex has approved moving margenx.org's DNS to Cloudflare, and Abrey has agreed at the time; or Alex has chosen a separate small domain instead (D-009).
5. **The Cloudflare account** is one just for MargenX: logout and cancellations act on the whole account (research, section 1.8).

## 1. What runs

```
browser ──HTTPS──> Cloudflare Access (emailed one-time code, exact invited email only)
                        │  (checks the login, adds a signed token to every request)
                        ▼
                    Cloudflare's network
                        ▲
                        │  the tunnel connects OUT from the copy; nothing connects in
┌─ one container on the host (Render background worker: no public address) ───────────┐
│  deploy/trial/launch.py                                                               │
│    ├─ cloudflared (pinned version, checksum checked at build): "Protect with Access"  │
│    └─ MargenX (Streamlit, trial_app.py) on 127.0.0.1:8501 only                        │
│         └─ TrialGate (trial_access.py): checks the token again on every request,      │
│            exact host, live connections, logout, no-store; refuses every upload       │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

**The image** (`deploy/trial/Dockerfile`) is built from the repository root **for linux/amd64**: `docker build --platform linux/amd64 -f deploy/trial/Dockerfile .`. The build fails on any other machine type. The image holds:
- Python 3.11.18 slim, pinned by its digest;
- cloudflared 2026.10.7, checked against its SHA-256 (`deploy/trial/fetch_cloudflared.py`);
- every Python package at the tested version, each checked against its hash, wheels only (`deploy/trial/requirements.lock`);
- **only** the files the trial page uses (`.dockerignore` keeps everything else out of the build folder);
- an ordinary user with no login shell.

It holds no setting, token or secret, and the Dockerfile declares **no build argument (`ARG`)**. `tests/test_trial_deploy.py` checks all of this.

**The launcher** (`deploy/trial/launch.py`):
- starts nothing unless every setting below is valid;
- starts MargenX, waits until it listens on the container, then starts the tunnel;
- **a stop always wins:** a stop that arrives while MargenX is still starting ends the wait at once, and the tunnel is never started;
- gives the token to the tunnel only, and the trial settings to MargenX only;
- **never restarts anything:** if either program stops, it stops the other and exits, so the whole copy stops;
- on the host's stop, stops MargenX first (no request is handled any more), then the tunnel, which has a 1-second grace period;
- never prints a setting's value or the token;
- **closed mode** (`MARGINX_TRIAL_CLOSED=1`): MargenX is given nobody's address (`closed@margenx.invalid`) instead of the invited email, so the copy itself refuses every login. The log says `closed: this copy refuses every login`. Used by the restart check (section 7).

**The tunnel runs with:**
- `--protocol http2` (TCP only);
- `--no-autoupdate`;
- `--management-diagnostics=false`: on by default, these let the dashboard take memory profiles of the traffic passing through;
- `--metrics 127.0.0.1:20241`: on the container only;
- `--loglevel info`: debug would log every header, tokens included.

## 2. The settings
They go in the host's environment settings. **None goes in the repository, an issue, a log or a screenshot.**

**How Render uses them:** Render gives them to the running copy, and **also passes them to the Docker build as build arguments**. The Dockerfile declares none, so the build neither uses nor stores them. The build log and the image are still checked for them (section 6).

| Setting | What | Secret? |
|---|---|---|
| `MARGINX_TRIAL` | `1` switches the trial on. Set but invalid makes the page refuse to run | No |
| `MARGINX_TRIAL_TEAM_DOMAIN` | `https://<team>.cloudflareaccess.com` (Zero Trust team domain) | No |
| `MARGINX_TRIAL_AUDIENCE` | The Access application's **AUD tag** (step 4.3) | No |
| `MARGINX_TRIAL_INVITED_EMAIL` | The one invited person's exact email. **For the operator-only copy: Alex's exact email** (D-009) | **Personal data**: only in the host's settings |
| `MARGINX_TRIAL_HOST` | The app's exact address, for example `app.margenx.org` | No |
| `TUNNEL_TOKEN` | The tunnel's token (step 4.5). **Added only at step 5, item 4** | **Yes** |
| `MARGINX_TRIAL_CLOSED` | `1` only for the restart check (section 7); otherwise not set | No |

**The same email goes in two places:**
- the Access allow rule (step 4.3, added last);
- `MARGINX_TRIAL_INVITED_EMAIL`.

Both are Alex's exact email for the operator-only copy, and MargenX refuses anyone else even if Access let them through.

## 3. Accounts
- **The four accounts:** a Cloudflare account just for MargenX, a Render account, and the existing Porkbun and GitHub accounts.
- **Two-step login on all four,** before any setup (section 0).

## 4. Cloudflare setup (nothing is reachable yet: the Access application lets nobody in until step 5, item 6)

### 4.1 The domain
- **Before the move,** copy every existing record into Cloudflare. **The live website is on Netlify** and its forms send through Formspree. Copy:
  - the website's records;
  - any email (MX) records;
  - any verification (TXT) records.
- **Then,** with Abrey and at a quiet time, change the name servers at Porkbun.
- **After the move,** check that the website, its forms and email still work.
- **If the move can't be done safely,** use a separate small domain (section 0).

### 4.2 Zero Trust
- **Team name:** choose one; it becomes `MARGINX_TRIAL_TEAM_DOMAIN`.
- **Login method:** under login methods, **add "One-time PIN"** (the emailed code). Since 2026-06-18 it isn't there by default.

### 4.3 The Access application (created with nobody allowed)
**Type and address:** a **Self-hosted** application for the app's exact address (for example `app.margenx.org`), with **no path**, so every address under it is covered: page, media, uploads and the live connection.

**Login methods:**
- **only One-time PIN**;
- **instant authentication** on.

**Session duration:** the plan's working-day length. Set the overall session to the same length.

**The allow rule:**
- **Not yet.** An application with no allow rule lets nobody in. The rule is added only at step 5, item 6.
- **When added:** **Allow**, with **Include → Emails → the one exact email**.
- **Never** "Everyone", the "login method = one-time PIN" selector, or "Bypass" on this app: Cloudflare's own page warns that the first two let anyone in.

**Copy the AUD tag:** copy the application's **AUD tag** into `MARGINX_TRIAL_AUDIENCE`.

### 4.4 Caching
Add a **cache rule: bypass cache** for the app's whole address. CSV and Excel are on Cloudflare's default cache list, and MargenX also says `no-store` on every response.

### 4.5 The tunnel
**Create it:** Networks → Tunnels → **Create a tunnel** (cloudflared), named for the copy (for example `margenx-trial-operator`).

**The token:** **copy the token, but don't give it to Render yet** (step 5, item 4). Don't run Cloudflare's install command anywhere: the container brings its own cloudflared.

**Public hostname:** exactly one, the app's address, with service **HTTP → `127.0.0.1:8501`**.
- **Other hostnames:** no other hostnames, and no catch-all.
- **Host header:** leave the HTTP host header setting empty, so MargenX sees the real address (its gate refuses any other).

**Under Access:** switch on **Protect with Access**, with the team name and the AUD tag above.

## 5. Render setup, in this order (a pinned build first; the token after; Access opened last)
Render's creation flow starts a first build at once, from the branch's latest commit. So the service is created **without the tunnel token**: whatever that first build is, the launcher refuses to start ("tunnel token missing") and nothing goes online.

1. **Create the service:** **New → Background Worker** (no public address, by design), connected to the GitHub repository.
   - **Language:** Docker.
   - **Dockerfile path:** `deploy/trial/Dockerfile`.
   - **Docker build context:** `.` (the repository root).
   - **Region:** a US region (Virginia, Ohio or Oregon). It can't be changed later.
   - **Instance size:** within Alex's budget. The final size comes from measuring the real copy (section 6, check 9, and PR B).
   - **Auto-Deploy: Off.**
   - **Environment:** the trial settings from section 2, **without `TUNNEL_TOKEN`** and without `MARGINX_TRIAL_CLOSED`. **No Secret Files** (Render copies them into the build folder), no disk, no cron job, no other service.
2. **Pin the build:** **Manual Deploy → Deploy a specific commit**, giving the **approved commit** (the merged commit Alex approved, recorded on #141 or #131).
3. **Verify, still offline:**
   - the deploy's commit in Render's events is exactly the approved one;
   - the log shows `margenx-trial: not starting: tunnel token missing: TUNNEL_TOKEN`;
   - in Cloudflare, the tunnel shows no connector.
4. **Add the token:** add `TUNNEL_TOKEN` with **"Save only"** (so no deploy starts by itself). Then **Manual Deploy → Deploy a specific commit** with **the same approved commit**.
5. **Verify, still with nobody allowed:**
   - the running deploy's commit is the approved one;
   - the log shows `margenx-trial: running`;
   - cloudflared registers its connections with **protocol http2**;
   - the tunnel shows **Healthy** in Cloudflare;
   - the app's address shows Cloudflare's login page, and **no email can get in**, because no allow rule exists yet.
6. **Open Access last:** add the allow rule with **Alex's exact email**, the same as `MARGINX_TRIAL_INVITED_EMAIL`.

**Deploying later:**
- only by hand (Manual Deploy → specific commit), and **never while someone is using a copy**: Render runs two copies for a short time during a deploy;
- between uses, stop first (section 7);
- a changed setting is saved with "Save only" and then deployed deliberately.

**Restarts:** Render restarts a *running* copy that stops by itself. That's a running copy, not an ended trial. **A Suspended service stays stopped** until someone presses Resume (section 8).

## 6. The operator-only test copy's checks (made-up files only; results on PR #141 before merge)
The plan checks PR A by "a run against the operator-only copy, with results on the PR". These checks come from the PR #137 round-1 review (test requirements for A2) and the PR #141 round-1 review. Each is recorded on #141 **in words only**: no email, token, cookie, or screenshot showing them.

1. **The built image.**
   - The build of the approved commit succeeded on Render, for linux/amd64.
   - **The build log** contains no token, no invited email and no setting value. Render passes settings as build arguments; the Dockerfile uses none, so at most a warning names unused arguments.
   - **The image itself:** where Docker is available, build the same commit with made-up marker values passed as build arguments, the way Render does: `docker build --platform linux/amd64 --build-arg TUNNEL_TOKEN=marker-token --build-arg MARGINX_TRIAL_INVITED_EMAIL=marker@example.com ...`. Then search `docker history --no-trunc` and `docker inspect` for the markers: there must be none.
2. **Start, and setup steps 3 and 5,** as recorded during section 5.
3. **Only through the tunnel.**
   - The Render service has no public address.
   - Without logging in, the app's address shows Cloudflare's login page, never MargenX.
   - In the running copy (Render's Shell), the listening sockets are only `127.0.0.1:8501` (MargenX) and `127.0.0.1:20241` (cloudflared's metrics). Read them with `python -c "print(open('/proc/net/tcp').read())"`; the slim image has no `ss` or `netstat`.
4. **The real login, everywhere.** After Alex's emailed code:
   - the page loads (made-up samples only);
   - the live connection works (the page reacts);
   - media loads;
   - a direct `PUT` to `/_stcore/upload_file/...` **is refused**, because uploads are off.
   - **An uninvited email gets no working code.**
5. **Public response headers.** Using the browser's developer tools on the app's responses, check that they carry:
   - `Cache-Control: no-store`;
   - `X-Frame-Options: DENY`;
   - `Referrer-Policy: same-origin`;
   - `Content-Security-Policy` with `frame-ancestors 'none'`;
   - and that **Cloudflare hasn't added another referrer policy** (a `no-referrer` would break the Log out form; PR #137).
6. **Log out through real Cloudflare.**
   - **Log out** posts, and lands on Cloudflare's logout.
   - A second tab is cut off.
   - Logging back in needs a new code.
   - Note how long Cloudflare's logout takes.
7. **The stop procedure (section 7) on this copy,** including its restart check. With a results tab open, step 1 (Suspend) must cut the tab within seconds. **Afterwards,** re-add Alex's email and remove `MARGINX_TRIAL_CLOSED` only if the copy is to be used again.
8. **Logs hold no secrets.** Search Render's logs, cloudflared's lines included, for:
   - the token;
   - `CF_Authorization` and the assertion header's value;
   - Alex's email;
   - the sample file names;
   - any file contents.
   - Uploads are off, so the file-bytes and marker searches belong to the uploads PR and release check 6.
9. **Memory.** Note the copy's memory in Render's metrics, idle and with two tabs on the samples. This is for sizing; the worst-case measurement is in PR B.

**If any check fails,** the copy is stopped (section 7, step 1), the problem is fixed in a PR, and the affected checks are run again.

## 7. The stop procedure (closeout, early end, emergency: always the same, in this order)
1. **Stop the copy.**
   - On Render: the service → **Suspend**.
   - This ends the app and the tunnel, and it's what cuts open tabs and uploads.
2. **Remove the email from the Access rule.**
   - Zero Trust → Access → Applications → the app → its rule → delete the email.
   - If it was the only email, the application now lets nobody in.
3. **Revoke its Access sessions.**
   - Zero Trust → Team & Resources → Users → the email → **Revoke session**.
4. **Verify the cutoff.**
   1. An open tab has lost its connection: leave it open, unreloaded, for step vi.
   2. A slow upload didn't finish being processed. That applies once uploads are on; release check 5.
   3. **The restart check: the copy itself refuses the former invite.** Set `MARGINX_TRIAL_CLOSED=1` on the copy with **"Save only"**.
   4. **Wait at least one minute after step 3.** Cloudflare blocks a revoked person's re-login for up to a minute, and a refusal during that minute proves nothing.
   5. **Resume the copy and confirm it's healthy:**
      - the log shows `margenx-trial: closed: this copy refuses every login`, then `margenx-trial: running`;
      - the running deploy's commit is the approved one;
      - the tunnel is **Healthy** in Cloudflare.

      If the `closed` line doesn't appear, the setting didn't reach the copy: Suspend, then **Manual Deploy → the approved commit**, which starts it with the current settings, and confirm again. Only test a copy that is running and healthy: a refusal from a stopped tunnel proves nothing.
   6. **Test both ways back in:**
      - the **original signed-in browser**: reload the tab left open in step i (it reconnects with its old login);
      - **a fresh login** with the former email.

      Both must be refused.
   7. **Suspend again, whatever the result.** If anything got in, treat it as an incident: the copy stays suspended, and Alex is told at once.

**Removing the email or revoking sessions without stopping the copy never ends a trial:** an already-open live connection may stay open.

## 8. Nothing brings an ended trial back by itself
- **Render:** a Suspended service stays suspended until someone presses **Resume**. Nobody presses Resume, Restart or Manual Deploy on an ended trial's copy, except for the restart check (section 7, step 4), which ends suspended again.
- **No pushes, no schedules:**
  - Auto-Deploy is off, so a push to GitHub doesn't deploy.
  - There is no cron job or scheduled job.
- **The launcher:** never restarts a program. If one stops, the whole copy stops.
- **The tunnel:** with the copy stopped, nothing connects to it. Cloudflare shows its own error page, and MargenX is unreachable.

## 9. Changing anything
- **During a trial,** nothing changes except in an emergency, and then the stop comes first.
- **A change to the code, packages, cloudflared, the base image or any setting** means a new approved commit, and the release checks it could affect run again (plan section 3.5) before any shop uses it.
- **Updating a pin** is always a PR:
  - cloudflared: `VERSION` and `SHA256` in `fetch_cloudflared.py`, checked against the release's published checksum;
  - the base image: the digest in the Dockerfile;
  - packages: regenerate `requirements.lock` as its header says.

## 10. Not in this PR (later steps)
- **The uploads-on PR** (after #128's reading is ready). It covers:
  - consent;
  - a consent withdrawal that is safe against an upload in flight;
  - file, unpacked-size, time and concurrency limits;
  - no upload bytes left on disk or in Streamlit's storage after cleanup;
  - making sure no error log quotes a file's contents (logs can't be switched off on the hosts).
- **PR B:**
  - the six release checks on this exact setup;
  - the trial terms;
  - the one-page guide;
  - Alex's checklist;
  - the two follow-ups from PR #137: a total deadline for fetching Cloudflare's keys, with bounded parallel checks; and cutting open live connections when Cloudflare retires a key.
- **The provider retention evidence** (plan section 3.4). Real files stay off until it's complete for the exact host and data path.
- **The website:** its Log in link set to the app's address with no password form, and its Privacy Policy matching the emailed-code login (issue #131 comment of 2026-11-04). This needs fixing before any shop is invited.
