# The website trial's release checks (PR B and the uploads PR, issue #131)

**Status:** this is the runbook. **Nothing is deployed, bought or switched on by this document or its PR.** The checks run on the operator-only copy (D-009, part 1: Alex only, made-up files only), on PR B's exact head, after Alex approves that commit on PR B (`docs/TRIAL_DEPLOYMENT.md`, section 0). Results go on PR B **in words only**: no email, token, cookie, or screenshot showing them.

**The one combined run (Alex, 2026-11-17 and 2026-11-23):** the whole run, the "Now (PR B)" parts and the "Uploads PR" parts below, happens **once, on the uploads PR's exact head**, after Alex approves that commit on the uploads PR. Every upload uses **made-up files only** (the operator-only copy, D-009 part 1).

**Scope (Alex, 2026-11-17, recorded on #131): PR B without uploads.** Trial uploads stay off (PR #137). So PR B runs every part of the six release checks that works with the made-up samples, and marks the rest **"uploads PR"**: those parts run in the PR that switches trial uploads on, on that PR's exact head. **No shop is invited until every part of all six checks has passed** on the exact version and settings the shop will use (plan section 3.5).

## What PR B changes, in plain words
| Change | Why | Where |
|---|---|---|
| **Stop-now** | Render's Suspend takes about 2 minutes to reach the copy (#141). The stop-now, run in Render's Shell, should cut open tabs within seconds (under 3 s in local tests with stand-ins; Render's time is measured in check 5) | `deploy/trial/stop_now.py`, `launch.py` |
| **Closed mode's own refusal** | B4 could show it only by a log line: with no Access rule, Cloudflare refuses first. Now MargenX's refusal says "This MargenX trial copy is closed." and carries `X-MargenX-Gate: closed` | `trial_access.py` |
| **The self-check** | Proves, from inside a running copy, that MargenX itself refuses requests that skip Cloudflare | `deploy/trial/self_check.py` |
| **A total deadline and a cap on login checks** (PR #137 follow-up) | A slow fetch of Cloudflare's keys could hold up other checks, a logout included. Now a check is refused after 8 s, and at most 8 run at once | `trial_access.py` (`TokenChecks`) |
| **Open tabs checked against Cloudflare's current keys** (PR #137 follow-up) | A key Cloudflare removed didn't cut an already-open tab. Now each open tab's login is checked again every 60 s, and closed if refused or if the check can't finish. A removed key cuts an open tab within about 6 minutes 10 seconds (the 5-minute cached key set, the next re-check 60 s later, and that check's 8-second deadline, plus a moment of scheduling) | `trial_access.py` |

The unit tests are in `tests/test_trial_release.py` and `tests/test_trial_deploy.py`. Each change was undone on purpose, one at a time, and the tests failed every time (list on PR B).

## What the uploads PR changes, in plain words (plan v7, reviewed PASS WITH WARNINGS on #131)
| Change | Why | Where |
|---|---|---|
| **One consent per MargenX process, for one tab** | Only the tab that pressed "I agree" can add files, and only while it is the only MargenX tab | `trial_access.py` (`TrialState`) |
| **Every ending ends the process** | End session, Log out, a closed or reloaded tab, a dropped connection, an expired login: the launcher kills MargenX's process group and starts a fresh, empty one. Nothing from the old one can be read, finished or sent | `deploy/trial/launch.py`, `trial_control.py` |
| **The launcher supervises MargenX** | A 60 s limit on reading a file, a 15 s heartbeat, a 1.2 GB memory limit, enforced from outside MargenX; no core dumps | `deploy/trial/launch.py` |
| **Logouts survive restarts** | The launcher keeps the logout time and gives it to every new MargenX; after an unexplained ending, every earlier login must log in again | `trial_control.py`, `trial_access.py` |
| **Every upload checked before its body is read** | Login, Origin, Streamlit's XSRF token, the consented session, an unused address issued to it, the size; a 120 s deadline | `trial_access.py` (`TrialGate`, the upload store) |
| **Bad files refused first** | At most 5 MB; an Excel file at most 25 MB unpacked, 100 parts, no part over 1 MB packed more than 100 times | `upload_limits.py` |
| **Nothing on disk, nothing in logs** | Uploaded parts stay in memory; errors show a plain message and log no file name or content | `trial_app.py`, the page |

The unit and process tests are in `tests/test_trial_uploads.py`, `tests/test_trial_supervisor.py` and `tests/test_trial_stack.py`. Each check was undone on purpose, one at a time (list on the uploads PR).

## Before the run
- The uploads PR's manual review has passed on its exact head (PR B's has too), and Alex has approved that commit for the operator-only run in a comment on the uploads PR giving its full hash.
- **A new tunnel and token** (the operator tunnel was deleted after B4, #141): create it, its one public hostname with Protect with Access, as in `docs/TRIAL_DEPLOYMENT.md`, section 4.5. The token is pasted into Render by Alex only.
- **Made-up upload files ready** (never real ones): a made-up Profit and Loss Detail and Sales by Customer Detail built from `sample_data` (the #128 accuracy fixtures); a copy whose file name and contents carry unique marker text (for check 6); a broken file; a file over 5 MB; a highly compressed one; a file that isn't a QuickBooks report.
- Render: the service's branch is the uploads PR's branch; **Manual Deploy → that exact commit**, then the guide's section 5 order: verified offline first, the token second, Alex's exact-email allow rule last.
- **Budget:** the copy is billed by the second while it runs, within Alex's approved $30 a month. Suspend it as soon as the run ends.

## The six checks

### 1. Access and bypass
**Now (PR B):**
- Signed out, the app's address, `/_stcore/health`, `/media/...`, `/_stcore/upload_file/...` and the live connection all go to Cloudflare's login (B4 part 3 for the page and health; repeat for each).
- **Around the gate, from inside the copy:** in Render's Shell, `python /app/deploy/trial/self_check.py` must end with `all refused by MargenX itself; the copy is in open (invited person only)`. It covers: no login, a forged login for the invited email, another host name, the upload address, data sent to the page, Log out by GET and from another site, media, and the live connection. Each must get MargenX's own marked 403 (`X-MargenX-Gate`), the live connection included; a probe that can't run fails the check. These probes carry no valid login: the cross-site checks for a logged-in person are covered by the unit tests and the next bullets.
- An uninvited email gets no working code (B4 part 7 (b): a plus-alias of Alex's address got none); repeat once on this build.
- **A pending invite** (plan test requirement 1): with the allow rule not yet added (section 5, item 5), Alex's own email gets no working code.
- **Other host names:** only `app.margenx.org` reaches the copy. `margenx.org` and `www` still go to Netlify; any other name under the domain has no route.
- **The server itself** has no public address (B4 part 5, check 3: background worker; only `127.0.0.1:8501` and `127.0.0.1:20241` listening). Repeat the socket check on this build.
- **Cross-site:** a page on another site can't open the live connection (the gate checks Origin) or log Alex out (unit tests in `tests/test_trial_access.py`; the self-check's cross-site Log out probe).

**Uploads PR:**
- **The upload address with a valid login but no consent:** in the browser's developer tools, copy a `PUT` request to `/_stcore/upload_file/...` from a session that hasn't pressed "I agree", and replay it: **403 with `X-MargenX-Gate: refused`**, and nothing appears on the page.
- **A cross-site upload with a valid login:** the same replay with another `Origin`, or from a page on another site: refused the same way.
- **One tab only:** with two tabs open, "I agree" says "Close your other MargenX tabs first"; after consent in one tab, a second tab can't connect.

### 2. Consent and bad files
**Uploads PR,** all of it:
- **A direct upload before consent fails** (check 1's replay).
- **Withdrawal against a slow upload:** throttle the browser (developer tools, "Slow 3G"), start uploading the made-up Profit and Loss Detail, and press **End session** before it finishes. The page shows "Clearing…", reloads to a fresh page within seconds (the log: `recycled: session ended`), and **no result from that file ever shows**. Repeat with **Log out**, and with closing the tab.
- **Broken, oversized and highly compressed files:** each gets its plain refusal; a file that isn't a QuickBooks report gets "MargenX's trial reads only...". Nothing else happens.
- **A slow or interrupted upload:** an upload throttled past 120 s is refused; turning Wi-Fi off mid-upload ends the session (recycled; the page reloads when back).
- **The limits:** 5 MB per file, 25 MB unpacked, 2 files held, 4 upload addresses per session ("End session to start again"), one reading at a time.
- **A file that takes too long:** not reproducible with a real export; covered by the unit tests (`work took too long`). Record the time the largest made-up file takes to read (check 6).

**Now (PR B):** with a valid login, a direct `PUT` and `POST` to `/_stcore/upload_file/...` are refused (403 with `X-MargenX-Gate: refused`), because uploads are off (B4 part 5 showed 403; this run also checks the header).

### 3. Money
**Uploads PR:** upload the made-up export (both reports) in the trial; hosted and local results match on the same made-up export, and both match independently known totals (the #128 accuracy tests: `docs/ACCURACY.md`, sections 5 to 7), including a missing cost, a rejected row, ambiguous and duplicate inputs, credits or refunds, payouts and deposits kept out of sales, and unsupported QuickBooks variants refused.

**Now (PR B):** the trial's made-up samples show the same figures online as on the laptop: the sign shop's $11,000 in sales over 8 jobs (B4 part 5) and the contractor's $77,400. Note any difference.

**The coverage decision, settled and built (Nov 17): D-010, PR #148 and #149.** Found while preparing PR B: the QuickBooks reading at the time let customer figures and the overall total show Complete from a Profit and Loss Detail alone, even with a whole cost account filtered out. PR B's manual review (round 1) said it must be resolved before trial uploads are switched on. Alex chose "Needs a check": now every figure, the overall total included, shows Needs a check (missing amount unknown) until the owner confirms the file's coverage, and the results say what Complete relies on. **The uploads PR's checks run on code that includes it**, and include a made-up export with a cost account left out: with no coverage answer, nothing is Complete.

### 4. Cleanup and isolation
**Now (PR B),** with two tabs on the samples:
- **Log out across tabs:** Log out in tab A; tab B loses its connection within seconds and can't reconnect; a reload needs a fresh code (B4 part 5, check 6: about 30 s at Cloudflare).
- **The back button and history:** after Log out, Back and a history entry show nothing new (responses are `no-store`); any reload needs a fresh code.
- **Reconnecting:** turn the Mac's Wi-Fi off for 20 s and on again with a tab open; it reconnects to the same session while the login is valid.
- **Disconnect cleanup:** close a tab; Streamlit drops its session after 10 s (`disconnectedSessionTTL`).
- **Old session after switching "shops":** with copy "shop A" stopped (stop procedure) and started again as "shop B" (a fresh process; for this run, the same operator email and different made-up samples), the tab left open from "shop A" gets nothing from "shop A": it needs a fresh code (its sessions were revoked), and after that it shows only "shop B"'s fresh page. The new process holds nothing from the old one.

**Uploads PR:**
- **An old upload address from "shop A" against "shop B":** with "shop A"'s made-up file uploaded, copy its upload request; stop the copy (stop procedure) and start it as "shop B" with different made-up files; replay the old request: **refused before any body is read** (`X-MargenX-Gate: refused`). An old **media** address from "shop A" gets nothing (not found or refused).
- **After End session, the old upload address** is refused the same way (a fresh process holds nothing).
- **Reconnects:** with a file uploaded, turn Wi-Fi off for 20 s: the session ends, and the page reloads into a fresh one when back, with the consent box unticked and no file.

### 5. Closeout, early end and emergency stop
**Now (PR B),** three times (one each for closeout, early end and emergency), with a results tab open:
1. Open the copy's **Shell** first for the closeout run only; for the early-end and emergency runs, open it **after** Suspend, to learn whether Render still allows it.
2. Run the stop procedure (`docs/TRIAL_DEPLOYMENT.md`, section 7), with the stop-now.
3. **Record, in UTC to the second:** Suspend pressed; the stop-now asked; the `stopping now` and `stopped now` lines; **the open tab showing "Connecting"**; the tunnel Down; Render's later `stopping: asked to stop by the host` line; the route deleted.
4. **Pass, for each of the three runs:** the open tab is cut within **10 seconds** of the stop-now, and nothing restarts the copy until Resume. **If the Shell can't be opened after Suspend, the early-end and emergency runs FAIL**, even if the closeout passes: an emergency can't count on a Shell opened in advance, and would fall back to Render's ~2-minute stop. Check 5 then stays **blocked** until a revised emergency procedure (for example, the stop-now before Suspend) is reviewed, approved by Alex, and demonstrated in all three runs.
5. **The closed-mode proof** (the B4 gap), once, during the restart check: before resuming, keep **Alex's exact-email rule** on the Access application (the operator-only copy), set `MARGINX_TRIAL_CLOSED=1`, Resume, reconnect the route, and log in with Alex's code. **Pass:** the page says **"This MargenX trial copy is closed."**, and the browser's developer tools show the response header **`X-MargenX-Gate: closed`**. That request passed Cloudflare and was refused by MargenX itself. Also run the self-check in the Shell: it must say **closed mode**. Then finish the restart check as written (rule removed, sessions revoked, both ways back in refused), and Suspend again.

**Uploads PR:** the same three runs with a deliberately slow upload in progress (throttled, as in check 2): the upload can't finish being processed, and no result from it ever shows. The stop-now now kills MargenX's process group outright (log: `stopping now`); record the time from the stop-now to the open tab showing "Connecting".

### 6. Retention and release identity
**Now (PR B):**
- **Release identity:** Render's events show the exact approved commit; the image-marker check (`docs/TRIAL_DEPLOYMENT.md`, section 6, check 1) is repeated on this commit, since the image changed (two new files).
- **Logs:** Render's logs for the whole run have no token, no `CF_Authorization`, no assertion header value, no email, no sample file names and no file contents (as B4 part 5, check 8). The stop-now and self-check print no setting.
- **Caching:** every response checked carries `Cache-Control: no-store`, and Cloudflare shows `cf-cache-status: DYNAMIC` or `BYPASS`.
- **Expected outbound traffic,** documented: cloudflared to Cloudflare; MargenX to the team's own key address (`https://margenx.cloudflareaccess.com/cdn-cgi/access/certs`), about every 5 minutes while in use, and when a token has an unknown key. Nothing else: no analytics (`gatherUsageStats` off), no error reporting.
- **Render's written answer** on what its builder keeps (build arguments, attestations) and its retention (`docs/TRIAL_DEPLOYMENT.md`, section 6, check 1). **Until it's in, real files stay off** (plan section 3.4).

**Uploads PR:**
- **Markers:** upload the made-up file whose **name** and **contents** carry unique marker text: once successfully (its results may show the content marker: that's the person's own result), once refused (no consent, by replay), once broken. Then search **every** log and diagnostic we can see (Render's logs and events for the whole run, Cloudflare's logs for the hostname, the launcher's lines): **neither marker appears anywhere.** The unit tests also cover a forced failure in storage and in reading.
- **Memory and timing on the 2 GB copy (the caps are provisional until this):** MargenX's memory at start, idle, and while reading the largest made-up file twice (both boxes); the time that reading takes. Record them on the uploads PR. Only then may an address-space limit be set, at a value the whole image starts and works under.
- **Core dumps off:** in the Shell, `cat /proc/$(pgrep -f "streamlit run" | head -1)/limits | grep core` shows 0.
- **The way back in:** after an unexplained restart (in the Shell, `kill -9` MargenX's process), a reload shows "Your MargenX session was ended" with **Log in again**; pressing it leads to Cloudflare's login and a fresh code, and then back in (if refused right away, wait 30 s).

## How the results are recorded
One PR comment per check, in words, against the exact commit: what was done, the UTC times, pass or fail, and anything that differed. A failed check stops the run: the copy is stopped (section 7), the problem is fixed in a PR, and the affected checks run again.

## What this doesn't prove
- **Real shop files.** The run uses made-up files only. Real files also need Render's and Cloudflare's written retention answers, the signed terms and Alex's yes for that shop.
- **Render's Shell after Suspend** until check 5 has measured it.
- **Other hosts or settings.** Each check holds only for the exact build and settings it ran on. A change re-runs the checks it could affect (plan section 3.5).
