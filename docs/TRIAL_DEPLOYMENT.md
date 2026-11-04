# The website trial: setup, operator-only test copy and stop procedure (PR A2, issue #131)

**Status:** this is the recipe. **Nothing is deployed, bought or switched on by this document or its PR.**

**What the operator-only test copy needs first:** Alex's decisions (issue #131, section 8):
- the server budget;
- the domain move;
- two-step login on the accounts;
- the Cloudflare account.

**What a shop's copy needs first:** everything in section 3.5 of the plan:
- the fit check;
- the signed terms;
- the retention evidence;
- PR B's release checks;
- Alex's yes for that shop;
- the invite added last.

**Trial uploads are off in the code** (PR #137). The trial shows MargenX's made-up samples only, until the PR that switches uploads on.

Sources: the plan (#131, lean v1.2), the hosting research (`docs/research/TRIAL_HOSTING_AND_LOGIN.md`), D-008 and D-009 (`docs/DECISIONS.md`), and the in-app checks (`trial_access.py`, PR #137).

## 1. What runs

```
shop's browser ──HTTPS──> Cloudflare Access (emailed one-time code, exact invited email only)
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

**The image** (`deploy/trial/Dockerfile`, built from the repository root) holds:
- Python 3.11.18 slim, pinned by its digest;
- cloudflared 2026.10.7, checked against its SHA-256 (`deploy/trial/fetch_cloudflared.py`);
- every Python package at the tested version, each checked against its hash, wheels only (`deploy/trial/requirements.lock`);
- **only** the files the trial page uses (`.dockerignore` keeps everything else out of the build, including any secret file a host drops into the build folder);
- an ordinary user with no login shell.

It holds no setting, no token and no secret. `tests/test_trial_deploy.py` checks all of this.

**The launcher** (`deploy/trial/launch.py`):
- starts nothing unless every setting below is valid;
- starts MargenX, waits until it listens on the container, then starts the tunnel;
- gives the token to the tunnel only, and the trial settings to MargenX only;
- **never restarts anything:** if either program stops, it stops the other and exits, so the whole copy stops;
- on the host's stop, stops MargenX first (no request is handled any more), then the tunnel, which has a 1-second grace period;
- never prints a setting's value or the token.

**The tunnel runs with:**
- `--protocol http2` (TCP only; the hosts don't document outbound UDP);
- `--no-autoupdate`;
- `--management-diagnostics=false`: on by default, these let the dashboard take memory profiles of the traffic passing through;
- `--loglevel info`: debug would log every header, tokens included.

## 2. The settings

They are given to the running copy only, in the host's environment settings. **None goes in the repository, an issue, a log or a screenshot.**

| Setting | What | Secret? |
|---|---|---|
| `MARGINX_TRIAL` | `1` switches the trial on. Set but invalid makes the page refuse to run | No |
| `MARGINX_TRIAL_TEAM_DOMAIN` | `https://<team>.cloudflareaccess.com` (Zero Trust team domain) | No |
| `MARGINX_TRIAL_AUDIENCE` | The Access application's **AUD tag** (step 4.3) | No |
| `MARGINX_TRIAL_INVITED_EMAIL` | The one invited person's exact email. For the operator-only copy: the operator's own | **Personal data**: only in the host's settings |
| `MARGINX_TRIAL_HOST` | The app's exact address, for example `app.margenx.org` | No |
| `TUNNEL_TOKEN` | The tunnel's token (step 4.5) | **Yes** |

**The same email is set in two places:**
- the Access allow rule (step 4.3);
- `MARGINX_TRIAL_INVITED_EMAIL`.

Both must change together; MargenX refuses anyone else even if Access let them through.

## 3. Accounts (once, before anything else)
- **Accounts:** a Cloudflare account **just for MargenX** (logout and cancellations act on the whole account; research section 1.8), a Render account, and the existing Porkbun and GitHub accounts.
- **Two-step login (MFA) on all four,** before any setup (plan section 2). Who turns it on is one of Alex's open decisions.
- **Spending:** nothing is bought before Alex approves a budget.

## 4. Cloudflare setup

### 4.1 The domain
- **Moving the DNS:** margenx.org's DNS moves to Cloudflare **once, with Abrey, at a quiet time** (plan section 2).
- **Before the move,** copy every existing record into Cloudflare. The **live website is on Netlify** and its forms send through Formspree. Copy:
  - the website's records;
  - any email (MX) records;
  - any verification (TXT) records.
- **Then** change the name servers at Porkbun.
- **After the move,** check that the website, its forms and email still work.
- **If this can't be done safely,** use a separate small domain just for MargenX (research section 1.8).

### 4.2 Zero Trust
- **Team name:** choose one; it becomes `MARGINX_TRIAL_TEAM_DOMAIN`.
- **Login method:** under login methods, **add "One-time PIN"** (the emailed code). Since 2026-06-18 it isn't there by default.

### 4.3 The Access application
**Type and address:** a **Self-hosted** application for the app's exact address (for example `app.margenx.org`), with **no path**, so every address under it is covered: page, media, uploads and the live connection.

**Login methods:**
- **only One-time PIN**;
- **instant authentication** on.

**Session duration:** the plan's working-day length. Set the overall session to the same length.

**The rule (policy):**
- **Allow**, with **Include → Emails → the one exact email**.
- **Never** "Everyone", the "login method = one-time PIN" selector, or "Bypass" on this app: Cloudflare's own page warns that the first two let anyone in.

**Copy the AUD tag:** copy the application's **AUD tag** into `MARGINX_TRIAL_AUDIENCE`.

### 4.4 Caching
Add a **cache rule: bypass cache** for the app's whole address. CSV and Excel are on Cloudflare's default cache list, and MargenX also says `no-store` on every response.

### 4.5 The tunnel
**Create it:** Networks → Tunnels → **Create a tunnel** (cloudflared), named for the copy (for example `margenx-trial-operator`).

**The token:** copy the token from the install command into the host's `TUNNEL_TOKEN`. Don't run Cloudflare's install command anywhere: the container brings its own cloudflared.

**Public hostname:** exactly one, the app's address, with service **HTTP → `127.0.0.1:8501`**.
- **Other hostnames:** no other hostnames, and no catch-all.
- **Host header:** leave the HTTP host header setting empty, so MargenX sees the real address (its gate refuses any other).

**Under Access:** switch on **Protect with Access**, with the team name and the AUD tag above.

## 5. Render setup (the first host to test; Fly.io is the fallback)
**Create the service:** **New → Background Worker** (no public address, by design). Connect the GitHub repository.
- **Language:** Docker.
- **Dockerfile path:** `deploy/trial/Dockerfile`.
- **Docker build context:** `.` (the repository root).

**Region:** a US region (Virginia, Ohio or Oregon). It can't be changed later.

**Instance size:** chosen with Alex's budget. The final size comes from measuring the real copy at the plan's worst case (research section 3); until then, a size the budget allows for made-up files only.

**Auto-Deploy: Off.** A push to GitHub must never start or change a copy.

**Environment:**
- add the six settings from section 2 as environment variables;
- **don't use Secret Files,** because Render copies them into the build folder. `.dockerignore` keeps them out of the image anyway, but there's no need for them;
- when changing a setting on a copy that is in use, use **"Save only"**, then deploy deliberately.

**No disk, no cron job, no other service.**

**Deploying:** only by hand, with **Manual Deploy → Deploy a specific commit**, giving the approved commit. Record that commit.

**Render runs two copies for a short time during a deploy.** So **never deploy while someone is using a copy.** Between uses: stop (section 7), then deploy.

**Restarts:**
- Render restarts a *running* copy that stops by itself. That's a running copy, not an ended trial.
- **A Suspended service stays stopped** until someone presses Resume (section 8).

## 6. The operator-only test copy (made-up files only)
This is the plan's "run against the operator-only copy". The invited email is the operator's own, and **no shop is involved**. Each check below is run on the copy and recorded on the PR **in words only**: no email, token, cookie or screenshot showing them. These checks come from the PR #137 round-1 review, test requirements for A2.

1. **Start and logs.**
   - Render's log shows `margenx-trial: running`.
   - cloudflared registers its connections with **protocol http2**.
   - **No** debug lines.
2. **Only through the tunnel.**
   - The Render service has no public address.
   - The app's address, without logging in, shows Cloudflare's login page, never MargenX.
   - MargenX itself refuses any other host name (its gate; already tested locally).
3. **The real login, everywhere.** After the emailed code:
   - the page loads (made-up samples only);
   - the live connection works (the page reacts);
   - media loads;
   - a direct `PUT` to `/_stcore/upload_file/...` **is refused**, because uploads are off.
   - **An uninvited email gets no working code.**
4. **Public response headers.** Using the browser's developer tools on the app's responses, check that they carry:
   - `Cache-Control: no-store`;
   - `X-Frame-Options: DENY`;
   - `Referrer-Policy: same-origin`;
   - `Content-Security-Policy` with `frame-ancestors 'none'`;
   - and that **Cloudflare hasn't added another referrer policy** (a `no-referrer` would break the Log out form; PR #137).
5. **Log out through real Cloudflare.**
   - **Log out** posts, and lands on Cloudflare's logout.
   - A second tab is cut off.
   - Logging back in needs a new code.
   - Note how long Cloudflare's logout takes (its documents say 20–30 seconds).
6. **The stop procedure (section 7) closes live connections.** With a results tab open, Suspend the copy.
   - The tab loses its connection within seconds.
   - With the email removed, Resume: the email can't get back in.
   - Suspend again.
7. **Logs hold no secrets.** Search Render's logs and cloudflared's lines for:
   - the token;
   - `CF_Authorization` and the assertion header's value;
   - the operator's email;
   - the sample file names;
   - any file contents.
   - Uploads are off, so the file-bytes and marker searches belong to the uploads PR and release check 6.
8. **Memory.** Note the copy's memory in Render's metrics, idle and with two tabs on the samples. This is for sizing; the real worst-case measurement is in PR B.

**If any check fails,** the copy is stopped (section 7), the problem is fixed in a PR, and the affected checks are run again.

## 7. The stop procedure (closeout, early end, emergency: always the same, in this order)
1. **Stop the copy.**
   - On Render: the service → **Suspend**.
   - This ends the app and the tunnel, and it's what cuts open tabs and uploads.
2. **Remove the email from the Access rule.**
   - Zero Trust → Access → Applications → the app → its rule → delete the email.
3. **Revoke its Access sessions.**
   - Zero Trust → Team & Resources → Users → the email → **Revoke session**.
4. **Verify the cutoff.**
   - An open tab has lost its connection.
   - A slow upload didn't finish being processed. That applies once uploads are on; release check 5.
   - The removed email can't get back in, even after a restart. Resume the copy with the email removed, try, then Suspend again.

**Removing the email or revoking sessions without stopping the copy never ends a trial:** an already-open live connection may stay open.

## 8. Nothing brings an ended trial back by itself
- **Render:** a Suspended service stays suspended until someone presses **Resume**. Never press Resume, Restart or Manual Deploy on an ended trial's copy, except for the restart check in section 7, step 4.
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
- **Alex's go-live decisions:**
  - the budget;
  - the domain move;
  - two-step login on the accounts;
  - the closeout backup (Abrey, recorded);
  - the website's Log in link set to the app's address with no password form, and its Privacy Policy matching the emailed-code login (issue #131 comment of 2026-11-04).
