# The website trial: setup, operator-only test copy and stop procedure (PR A2 and PR B, issue #131)

**Status:** this is the recipe. **Nothing is deployed, bought or switched on by this document or its PR.** Trial uploads are off in the code (PR #137): a copy shows MargenX's made-up samples only, until the PR that switches uploads on.

**What the operator-only test copy is (D-009, part 1):** MargenX online behind Cloudflare Access, with **only Alex invited** (his exact email) and **made-up files only**. No shop can reach it. **What a shop's copy needs:** D-009 part 2 and D-008, in their order, with the invite added last. This document doesn't cover shop copies beyond the stop procedure.

Sources: the plan (#131, lean v1.2), the hosting research (`docs/research/TRIAL_HOSTING_AND_LOGIN.md`), D-008 and D-009 (`docs/DECISIONS.md`), and the in-app checks (`trial_access.py`, PR #137).

**PR B adds** (details in `docs/TRIAL_RELEASE_CHECKS.md`): the operator's **stop-now** (section 7, step 1.ii), the **self-check** run inside a copy (`deploy/trial/self_check.py`), **closed mode's own refusal**, marked so it can be told apart from Cloudflare's (section 7, step 4.vii), and the release checks that work while uploads are off.

## 0. Before anything goes online (prerequisites, all recorded on #131)
1. **Two-step login (MFA)** is on for all four administrator accounts: Cloudflare, the host, Porkbun and GitHub (D-009, item 1).
2. **Alex has approved a budget.** Nothing is bought before that (D-009).
3. **Alex has chosen the host,** recorded on #131 (D-009: "chosen by Alex before the deployment"). The steps below are for **Render**, the research's first choice. A different host needs its own steps, reviewed first.
4. **The domain:** Alex has approved moving margenx.org's DNS to Cloudflare, and Abrey has agreed at the time; or Alex has chosen a separate small domain instead (D-009).
5. **The Cloudflare account** is one just for MargenX: logout and cancellations act on the whole account (research, section 1.8).
6. **Docker Desktop on Alex's Mac,** for the required image check (section 6, check 1). It's free for a business our size.

**The approved commit** (what "approved" means everywhere below):
- **For the operator-only test copy:** the exact head commit of PR #141, **unmerged**. It may run only after:
  - the PR's manual review has passed on that exact commit;
  - Alex has said, in a comment on #141 giving its full commit hash, that this commit may run as the operator-only copy.

  The Render service's branch is then the PR's branch, `margenx/trial-a2-deploy`, because Render deploys commits from the service's branch. The results go on #141, against that commit, **before** the merge.
- **If the PR's head changes after the run** (a fix, or bringing the branch up to date with `main` for the merge):
  - a change to any file the image is built from (the Dockerfile, `.dockerignore`, the lock, `fetch_cloudflared.py`, `launch.py`, or any file in the Dockerfile's `COPY` list) means the run is repeated on the new head, approved the same way, before the merge;
  - a change to none of them (docs or tests only) is recorded on #141 with its file list, and the results stand.
- **For PR B's release run** (`docs/TRIAL_RELEASE_CHECKS.md`): the exact head commit of PR B, **unmerged**, approved the same way on PR B's own pull request, with the service's branch set to PR B's branch. The same rule applies if its head changes.
- **For a shop's copy:** a commit on `main`, approved by Alex for that copy and recorded on #131, after PR B's release checks.

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
- **a stop always wins:**
  - a stop that arrives while MargenX is still starting ends the wait at once, and the tunnel is never started;
  - **no stop can slip in between the last check and the tunnel's start:** from that check until the tunnel exists, the host's stop signals are held back and then looked at. A stop that arrived before the start means the tunnel is never started. One that arrives during the start itself, the few milliseconds of creating the process, means the new tunnel is killed at once, without its grace period;
- gives the token to the tunnel only, and the trial settings to MargenX only;
- **never restarts anything:** if either program stops, it stops the other and exits, so the whole copy stops;
- on the host's stop, stops MargenX first (no request is handled any more), then the tunnel, which has a 1-second grace period;
- never prints a setting's value or the token;
- **closed mode** (`MARGINX_TRIAL_CLOSED=1`): MargenX is given nobody's address (`closed@margenx.invalid`) instead of the invited email, so the copy itself refuses every login. The log says `closed: this copy refuses every login`. Since PR B, MargenX's gate then refuses **every** request before any login check, with the page text "This MargenX trial copy is closed." and the response header `X-MargenX-Gate: closed`. Used by the restart check (section 7);
- **the operator's stop-now** (PR B): `python /app/deploy/trial/stop_now.py`, run in Render's **Shell** on the running copy, makes the launcher stop MargenX, then the tunnel, **at once**. Every open tab and upload should be cut within seconds (under 3 s in local tests with stand-in programs; the time on Render is measured in PR B's release run). The launcher then **stays running and does nothing** (log: `stopped now: MargenX and the tunnel are stopped; waiting for the host's stop`), so Render never sees the copy end by itself and never restarts it. Suspend is still pressed (section 7).

**Every refusal by MargenX's gate** carries the header `X-MargenX-Gate`: `refused`, or `closed` in closed mode. A refusal without it came from something else, such as Cloudflare.

**The tunnel runs with:**
- `--protocol http2` (TCP only);
- `--no-autoupdate`;
- `--management-diagnostics=false`: on by default, these let the dashboard take memory profiles of the traffic passing through;
- `--metrics 127.0.0.1:20241`: on the container only;
- `--loglevel info`: debug would log every header, tokens included.

## 2. The settings
They go in the host's environment settings. **None goes in the repository, an issue, a log or a screenshot.**

**How Render uses them:** Render gives them to the running copy, and **also passes them to the Docker build as build arguments**. The Dockerfile declares none, so the build neither uses nor stores them. The build log and a local build of the same image, attestations included, are still checked for them, and Render is asked in writing what its builder keeps (section 6, check 1).

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
- **The login page shops see:** Reusable components → Custom pages → Access login page. Set the organization name to **MargenX**, and the header text to "Enter the email address MargenX invited. We'll email you a one-time code." Otherwise the page shows Cloudflare's auto-generated team name (seen in the B4 run, #141).

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
   - **Instance size:** within Alex's budget. The final size comes from measuring the real copy (section 6, check 9, and the uploads PR).
   - **Branch:** for the operator-only copy, the PR's branch `margenx/trial-a2-deploy` (section 0, "The approved commit"); for a shop's copy, `main`.
   - **Auto-Deploy: Off.**
   - **Environment:** the trial settings from section 2, **without `TUNNEL_TOKEN`** and without `MARGINX_TRIAL_CLOSED`. **No Secret Files** (Render copies them into the build folder), no disk, no cron job, no other service.
2. **Pin the build:** **Manual Deploy → Deploy a specific commit**, giving the **approved commit** (section 0): for the operator-only copy, PR #141's head as approved on #141.
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

**Suspend is not instant (measured three times in the B4 run, #141: 121 s, 120 s, 121 s):** Render shows "Suspended" at once, and stops billing, but it delivers the stop signal to the copy **about 2 minutes later**. Until then the copy keeps running and serving open tabs. Once the signal arrives, the launcher stops MargenX and then the tunnel within the same second. This is why the stop procedure (section 7) **presses Suspend first**, so the countdown starts at once, then runs the **stop-now** in Render's Shell (PR B), which cuts open tabs within seconds, and then deletes the tunnel's public hostname, which stops new requests. **Whether Render's Shell still opens on a copy after Suspend is pressed is measured in PR B's release run;** until then, for a planned closeout, open the Shell before pressing Suspend.

## 6. The operator-only test copy's checks (made-up files only; results on PR #141, against the approved commit, before merge)
The plan checks PR A by "a run against the operator-only copy, with results on the PR". These checks come from the PR #137 round-1 review (test requirements for A2) and the PR #141 round-1 review. Each is recorded on #141 **in words only**: no email, token, cookie, or screenshot showing them.

1. **The built image.**
   - The build of the approved commit succeeded on Render, for linux/amd64.
   - **The build log** contains no token, no invited email and no setting value. Render passes settings as build arguments; the Dockerfile uses none, so at most a warning names unused arguments.
   - **The image itself (required).** Render's built image can't be downloaded, so the same commit is built on Alex's Mac (Docker Desktop, section 0), the way Render builds it:
     - every setting from section 2 is passed as a build argument with an obviously made-up marker value;
     - a provenance attestation is made;
     - then the whole image is searched for the markers: every layer, the image settings and history, and the attestation.

     Run from a copy of the repository at the approved commit:
     ```
     docker buildx create --name margenx-check --driver docker-container --use
     docker buildx build --platform linux/amd64 -f deploy/trial/Dockerfile \
       --build-arg MARGINX_TRIAL=margenx-marker-1 --build-arg MARGINX_TRIAL_TEAM_DOMAIN=margenx-marker-2 \
       --build-arg MARGINX_TRIAL_AUDIENCE=margenx-marker-3 --build-arg MARGINX_TRIAL_INVITED_EMAIL=margenx-marker-4 \
       --build-arg MARGINX_TRIAL_HOST=margenx-marker-5 --build-arg TUNNEL_TOKEN=margenx-marker-6 \
       --build-arg MARGINX_TRIAL_CLOSED=margenx-marker-7 \
       --attest type=provenance,mode=min \
       --output type=oci,dest=margenx-check.tar,compression=uncompressed,force-compression=true .
     python3 - margenx-check.tar <<'EOF'
     import gzip, sys, tarfile
     compressed = unreadable = markers = provenance = 0
     with tarfile.open(sys.argv[1]) as tar:
         for member in tar:
             if not member.isfile():
                 continue
             data = tar.extractfile(member).read()
             if data[:2] == b"\x1f\x8b":  # gzip: read it decompressed
                 compressed += 1
                 data = gzip.decompress(data)
             elif data[:4] == b"\x28\xb5\x2f\xfd":  # zstd: this check can't read it
                 unreadable += 1
                 print("can't read (zstd):", member.name)
                 continue
             markers += data.count(b"margenx-marker")
             provenance += data.count(b"slsa.dev/provenance")
     print("compressed blobs, read decompressed:", compressed)
     print("unreadable blobs (must be 0):", unreadable)
     print("provenance mentions (at least 1):", provenance)
     print("markers (must be 0):", markers)
     EOF
     ```
     It must print **0 unreadable blobs, at least 1 provenance mention and 0 markers**.
     - The search reads every blob in the file, and **decompresses any compressed one first**. `compression=uncompressed` alone can leave reused layers compressed, so `force-compression=true` is set too, and a plain `grep` of the file isn't enough: it can't see inside a compressed layer.
     - Provenance in `mode=max` records build-argument values by design (Docker's documentation), so this image is never built with it.
   - **Render's own builder.** Render's image, and any attestation its builder makes, can't be inspected from outside. So:
     - the retention evidence (plan section 3.4) includes **Render's written answer**: does its build keep build arguments, or make provenance attestations, and in which mode?
     - **until that answer is in,** the tunnel token is treated as possibly kept by Render. After the operator-only run, that copy's tunnel is deleted in Cloudflare, so its token works nowhere, and no shop's copy starts;
     - **if Render keeps build arguments,** a shop's copy runs from an image built elsewhere instead of a Render build. That's a reviewed change (section 9).
2. **Start, and setup steps 3 and 5,** as recorded during section 5.
3. **Only through the tunnel.**
   - The Render service has no public address.
   - Without logging in, the app's address shows Cloudflare's login page, never MargenX.
   - **In the running copy (Render's Shell), IPv4 and IPv6:** the only sockets waiting for connections are TCP `127.0.0.1:8501` (MargenX) and TCP `127.0.0.1:20241` (cloudflared's metrics). Nothing in `tcp6`, and no UDP socket waiting for traffic. The slim image has no `ss` or `netstat`, so read the kernel's tables:
     ```
     python - <<'EOF'
     import socket
     def addr(h, v6):
         ip, port = h.split(":")
         b = bytes.fromhex(ip)
         if v6:
             b = b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4))
             return f"[{socket.inet_ntop(socket.AF_INET6, b)}]:{int(port, 16)}"
         return f"{socket.inet_ntop(socket.AF_INET, b[::-1])}:{int(port, 16)}"
     for name in ("tcp", "tcp6", "udp", "udp6"):
         try:
             rows = open(f"/proc/net/{name}").read().splitlines()[1:]
         except FileNotFoundError:
             print(name, "(not present)"); continue
         for row in rows:
             f = row.split()
             waiting = f[3] == "0A" if name.startswith("tcp") else set(f[2].split(":")[0]) == {"0"}
             if waiting:  # TCP: listening; UDP: bound and waiting for anyone's traffic
                 print(name, addr(f[1], name.endswith("6")))
     EOF
     ```
     It must print exactly `tcp 127.0.0.1:8501` and `tcp 127.0.0.1:20241`, plus "(not present)" for any table this kernel doesn't have.
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
7. **The stop procedure (section 7) on this copy,** including its restart check. With a results tab open, **record when the open tab is cut**, and the times of Suspend, the stop-now, the copy's `stopped now` and `stopping` log lines and the tunnel going down. The B4 run measured Render's Suspend alone: the tab was cut about **2 minutes** after Suspend (#141). The B4 follow-up measured the revised order: deleting the route stops new requests but leaves an open tab working until Render's stop (121 s after Suspend). PR B adds the stop-now and measures it (`docs/TRIAL_RELEASE_CHECKS.md`, check 5). **Afterwards,** re-add Alex's email and the public hostname, and remove `MARGINX_TRIAL_CLOSED`, only if the copy is to be used again.
8. **Logs hold no secrets.** Search Render's logs, cloudflared's lines included, for:
   - the token;
   - `CF_Authorization` and the assertion header's value;
   - Alex's email;
   - the sample file names;
   - any file contents.
   - Uploads are off, so the file-bytes and marker searches belong to the uploads PR and release check 6.
9. **Memory.** Note the copy's memory in Render's metrics, idle and with two tabs on the samples. This is for sizing; the worst-case measurement (large uploads) is in the uploads PR.

**If any check fails,** the copy is stopped (section 7, step 1), the problem is fixed in a PR, and the affected checks are run again.

## 7. The stop procedure (closeout, early end, emergency: always the same, in this order)
**Before a planned closeout** (a few minutes before the time): open the copy's **Shell** in Render (the service → Shell), so step 1.ii takes seconds. Abrey, as the backup, does the same.

1. **Stop the copy and cut its public route. Nothing waits on Cloudflare, and nothing waits on the Shell.**
   1. **Render, immediately:** the service → **Suspend**. Do this first, before anything else: Render shows "Suspended" at once, but the copy keeps running until Render delivers the stop signal, **about 2 minutes later** (section 5, "Suspend is not instant"), so the countdown should start as early as possible.
   2. **Render's Shell, right after: the stop-now.** In the copy's Shell, run:
      ```
      python /app/deploy/trial/stop_now.py
      ```
      It prints `stop-now: asked at …`, and within seconds the copy's log shows `stopping now: asked by the operator` and `stopped now: MargenX and the tunnel are stopped`. **This is what cuts an open tab and an upload in seconds** instead of 2 minutes (PR B; the times are measured in its release run). The copy then waits, doing nothing, for Render's own stop.
      - **If the Shell isn't open, won't open, or the command says no launcher is running or that it isn't ready to take a stop-now yet** (a copy still starting: the command waits up to 10 s, and never sends a signal that could end the launcher and make Render restart it), don't wait: Suspend is already under way. Go on to step iii, and note it in the record.
   3. **Cloudflare, right after:** in the tunnel's settings (Routes), **delete its public hostname** (the app's address → `127.0.0.1:8501`). New requests can then no longer reach the copy, and the address's DNS record is removed with it. Deleting the route alone **does not cut a tab that is already open** (the B4 follow-up, #141); the stop-now in step ii, or Render's own stop, does.
      - **If the route can't be deleted promptly** (Cloudflare unreachable, no access to the account, or the deletion stalls), don't wait for it: the Suspend from step i is already under way. Go on to step iv, keep trying the route, and record when it was finally deleted.
   4. **The stop is complete only when all of these are seen:** the tunnel shows **Down** (0 connections) in Cloudflare; the copy's log shows `stopped now` (from step ii) **or** `margenx-trial: stopping: asked to stop by the host`; and, in every case, Render shows the service **Suspended**. The launcher stops MargenX first, then the tunnel, which is what cuts open tabs and uploads. **Then confirm the route is deleted** (the tunnel's published routes are empty); if step iii was delayed, finish it now.
2. **Remove the email from the Access rule.**
   - Zero Trust → Access → Applications → the app → its rule → delete the email.
   - If it was the only email, the application now lets nobody in.
3. **Revoke its Access sessions.**
   - Zero Trust → Team & Resources → Users → the email → **Revoke session**.
4. **Verify the cutoff.**
   1. An open tab has lost its connection: leave it open, unreloaded, for step vii.
   2. A slow upload didn't finish being processed. That applies once uploads are on; release check 5.
   3. **The restart check: the copy itself refuses the former invite.** First, with the copy still suspended:
      - set `MARGINX_TRIAL_CLOSED=1` on the copy. A suspended service offers only a plain **"Save"**, which starts no deploy;
      - **confirm the public route is still disconnected** (step 1): the tunnel's list of public hostnames is empty. With no public hostname, the tunnel carries nothing to the copy, even while the copy runs.
   4. **Wait at least one minute after step 3.** Cloudflare blocks a revoked person's re-login for up to a minute, and a refusal during that minute proves nothing.
   5. **Resume the copy, and with the route still disconnected, confirm the setting took effect and the copy is healthy:**
      - the log shows `margenx-trial: closed: this copy refuses every login`, then `margenx-trial: running`, **from this start**: both lines come after this Resume's time in Render's events, and from the instance now running. An older line from an earlier start proves nothing;
      - the running deploy's commit is the approved one;
      - the tunnel's connector is **Healthy** in Cloudflare;
      - **the route is really off:** the tunnel's published routes are **empty**, and the running connector's latest `Updated to new configuration` log line shows **no ingress rule for the app's address**, only the catch-all `http_status:404`. A Cloudflare login page appearing at the address isn't proof by itself;
      - **public requests can't reach MargenX:** the app's address doesn't resolve, or shows only a Cloudflare page (its login or an error), never MargenX's page.

      - **MargenX itself refuses, from inside the copy:** in the copy's Shell, run `python /app/deploy/trial/self_check.py`. It must end with `all refused by MargenX itself; the copy is in closed mode` (PR B).

      **If the `closed` line doesn't appear, or the self-check doesn't say closed mode,** the setting didn't reach the copy: Suspend at once and leave the route disconnected. Then **Manual Deploy → the approved commit**, which starts it with the current settings, and confirm again. The route is never reconnected to a copy whose log doesn't show the `closed` line.
   6. **Only then reconnect the public route:** add back exactly the one public hostname, as in step 4.5 (HTTP → `127.0.0.1:8501`, the host header setting empty, **Protect with Access** on with the same team name and AUD tag).
   7. **Test both ways back in:**
      - the **original signed-in browser**: reload the tab left open in step i (it reconnects with its old login);
      - **a fresh login** with the former email.

      Both must be refused. Only test a copy that is running and healthy: a refusal from a stopped tunnel proves nothing.

      **With no Access rule left, Cloudflare refuses before MargenX is reached** (the B4 run, #141). MargenX's own refusal, through Cloudflare, is shown once on the operator-only copy in PR B's release run: with Alex's exact-email rule in place and closed mode on, Alex logs in, and the page says **"This MargenX trial copy is closed."** with the header `X-MargenX-Gate: closed` (`docs/TRIAL_RELEASE_CHECKS.md`, check 5). For a shop's copy, the `closed` line and the self-check in step v are the per-copy proof, on a build where that was shown.
   8. **Suspend again, whatever the result, then delete the public hostname again,** as in step 1: an ended trial's copy keeps no route. Wait for the `stopping` line and the tunnel showing Down, and confirm the routes are empty (step 1.iii). If anything got in, treat it as an incident: the copy stays suspended, and Alex is told at once.

**Removing the email or revoking sessions without stopping the copy never ends a trial:** an already-open live connection may stay open.

## 8. Nothing brings an ended trial back by itself
- **Render:** a Suspended service stays suspended until someone presses **Resume**. Nobody presses Resume, Restart or Manual Deploy on an ended trial's copy, except for the restart check (section 7, step 4), which ends suspended again, with no public route.
- **No pushes, no schedules:**
  - Auto-Deploy is off, so a push to GitHub doesn't deploy.
  - There is no cron job or scheduled job.
- **The launcher:** never restarts a program. If one stops, the whole copy stops.
- **After a stop-now** (section 7, step 1.ii), the launcher keeps both programs stopped and waits only for Render's stop. Nothing in the copy starts them again.
- **The tunnel:** with the copy stopped, nothing connects to it, and after the stop procedure it has no public hostname either. Cloudflare shows its own error page, and MargenX is unreachable.

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
  - making sure no error log quotes a file's contents (logs can't be switched off on the hosts);
  - **the upload parts of the release checks** (Alex, 2026-11-17: PR B without uploads): check 2, check 3's hosted run, the slow upload in check 5, upload markers in check 6, and the worst-case memory (`docs/TRIAL_RELEASE_CHECKS.md`).
- **PR B** (this guide's PR B additions are listed at the top): the release checks that work with the made-up samples, the stop-now, the self-check, closed mode's own refusal, the two PR #137 follow-ups (a total deadline and a cap on token checks; open live connections checked again against Cloudflare's current keys), and drafts of the trial terms (`docs/TRIAL_TERMS_DRAFT.md`), the one-page guide (`docs/TRIAL_SHOP_GUIDE.md`) and Alex's checklist (`docs/TRIAL_OPERATOR_CHECKLIST.md`).
- **The provider retention evidence** (plan section 3.4). Real files stay off until it's complete for the exact host and data path.
- **The website:** its Log in link set to the app's address with no password form, and its Privacy Policy matching the emailed-code login (issue #131 comment of 2026-11-04). This needs fixing before any shop is invited.
