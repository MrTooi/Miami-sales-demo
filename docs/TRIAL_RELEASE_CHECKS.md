# The website trial's release checks (PR B, issue #131)

**Status:** this is the runbook. **Nothing is deployed, bought or switched on by this document or its PR.** The checks run on the operator-only copy (D-009, part 1: Alex only, made-up files only), on PR B's exact head, after Alex approves that commit on PR B (`docs/TRIAL_DEPLOYMENT.md`, section 0). Results go on PR B **in words only**: no email, token, cookie, or screenshot showing them.

**Scope (Alex, 2026-11-17, recorded on #131): PR B without uploads.** Trial uploads stay off (PR #137). So PR B runs every part of the six release checks that works with the made-up samples, and marks the rest **"uploads PR"**: those parts run in the PR that switches trial uploads on, on that PR's exact head. **No shop is invited until every part of all six checks has passed** on the exact version and settings the shop will use (plan section 3.5).

## What PR B changes, in plain words
| Change | Why | Where |
|---|---|---|
| **Stop-now** | Render's Suspend takes about 2 minutes to reach the copy (#141). The stop-now, run in Render's Shell, cuts open tabs in about a second | `deploy/trial/stop_now.py`, `launch.py` |
| **Closed mode's own refusal** | B4 could show it only by a log line: with no Access rule, Cloudflare refuses first. Now MargenX's refusal says "This MargenX trial copy is closed." and carries `X-MargenX-Gate: closed` | `trial_access.py` |
| **The self-check** | Proves, from inside a running copy, that MargenX itself refuses requests that skip Cloudflare | `deploy/trial/self_check.py` |
| **A total deadline and a cap on login checks** (PR #137 follow-up) | A slow fetch of Cloudflare's keys could hold up other checks, a logout included. Now a check is refused after 8 s, and at most 8 run at once | `trial_access.py` (`TokenChecks`) |
| **Open tabs checked against Cloudflare's current keys** (PR #137 follow-up) | A key Cloudflare removed didn't cut an already-open tab. Now each open tab's login is checked again every 60 s, and closed if refused or if the check can't finish | `trial_access.py` |

The unit tests are in `tests/test_trial_release.py` and `tests/test_trial_deploy.py`. Each change was undone on purpose, one at a time, and the tests failed every time (list on PR B).

## Before the run
- PR B's manual review has passed on its exact head, and Alex has approved that commit for the operator-only run in a comment on PR B giving its full hash.
- **A new tunnel and token** (the operator tunnel was deleted after B4, #141): create it, its one public hostname with Protect with Access, as in `docs/TRIAL_DEPLOYMENT.md`, section 4.5. The token is pasted into Render by Alex only.
- Render: the service's branch is PR B's branch; **Manual Deploy → that exact commit**, then the guide's section 5 order: verified offline first, the token second, Alex's exact-email allow rule last.
- **Budget:** the copy is billed by the second while it runs, within Alex's approved $30 a month. Suspend it as soon as the run ends.

## The six checks

### 1. Access and bypass
**Now (PR B):**
- Signed out, the app's address, `/_stcore/health`, `/media/...`, `/_stcore/upload_file/...` and the live connection all go to Cloudflare's login (B4 part 3 for the page and health; repeat for each).
- **Around the gate, from inside the copy:** in Render's Shell, `python /app/deploy/trial/self_check.py` must end with `all refused by MargenX itself; the copy is in open (invited person only)`. It covers: no login, a forged login for the invited email, another host name, the upload address, data sent to the page, Log out by GET and from another site, media, and the live connection.
- An uninvited email gets no working code (B4 part 7 (b): a plus-alias of Alex's address got none); repeat once on this build.
- **A pending invite** (plan test requirement 1): with the allow rule not yet added (section 5, item 5), Alex's own email gets no working code.
- **Other host names:** only `app.margenx.org` reaches the copy. `margenx.org` and `www` still go to Netlify; any other name under the domain has no route.
- **The server itself** has no public address (B4 part 5, check 3: background worker; only `127.0.0.1:8501` and `127.0.0.1:20241` listening). Repeat the socket check on this build.
- **Cross-site:** a page on another site can't open the live connection (the gate checks Origin) or log Alex out (unit tests in `tests/test_trial_access.py`; the self-check's cross-site Log out probe).

**Uploads PR:** a cross-site upload with a valid login; the upload address with a valid login but no consent.

### 2. Consent and bad files
**Uploads PR,** all of it: a direct upload before consent fails; consent withdrawal against a slow upload; broken, oversized and highly compressed files; a slow or interrupted upload; the size, unpacked-size, time and concurrency limits.

**Now (PR B):** with a valid login, a direct `PUT` and `POST` to `/_stcore/upload_file/...` are refused (403 with `X-MargenX-Gate: refused`), because uploads are off (B4 part 5 showed 403; this run also checks the header).

### 3. Money
**Uploads PR:** hosted and local results match on the same made-up export, and both match independently known totals (the #128 accuracy tests: `docs/ACCURACY.md`, sections 5 to 7), including a missing cost, a rejected row, ambiguous and duplicate inputs, credits or refunds, payouts and deposits kept out of sales, and unsupported QuickBooks variants refused.

**Now (PR B):** the trial's made-up samples show the same figures online as on the laptop: the sign shop's $11,000 in sales over 8 jobs (B4 part 5) and the contractor's $77,400. Note any difference.

**Open decision before the uploads PR (found while preparing PR B; see PR B and #131):** the plan's coverage rule and its PR B test requirement ("unknown scope") say that when a file can't prove which jobs or customers an omitted cost account would affect, **every** affected job, customer and summary, **the overall total included**, shows Needs a check. Today's QuickBooks reading (#128, merged in PR #145) holds **jobs** from one report (S3), but **customer figures and the overall total can show Complete from a Profit and Loss Detail alone**: a made-up export with a whole cost account left out gives higher, Complete customer and company profit. The results say a filter can't be seen in the file, but the status still says Complete. **Alex decides** whether to change that (and how) before any real file is uploaded to a trial copy.

### 4. Cleanup and isolation
**Now (PR B),** with two tabs on the samples:
- **Log out across tabs:** Log out in tab A; tab B loses its connection within seconds and can't reconnect; a reload needs a fresh code (B4 part 5, check 6: about 30 s at Cloudflare).
- **The back button and history:** after Log out, Back and a history entry show nothing new (responses are `no-store`); any reload needs a fresh code.
- **Reconnecting:** turn the Mac's Wi-Fi off for 20 s and on again with a tab open; it reconnects to the same session while the login is valid.
- **Disconnect cleanup:** close a tab; Streamlit drops its session after 10 s (`disconnectedSessionTTL`).
- **Old session after switching "shops":** with copy "shop A" stopped (stop procedure) and started again as "shop B" (a fresh process; for this run, the same operator email and different made-up samples), the tab left open from "shop A" gets nothing from "shop A": it needs a fresh code (its sessions were revoked), and after that it shows only "shop B"'s fresh page. The new process holds nothing from the old one.

**Uploads PR:** an old **media or upload** address from "shop A" against "shop B", with different made-up files for each.

### 5. Closeout, early end and emergency stop
**Now (PR B),** three times (one each for closeout, early end and emergency), with a results tab open:
1. Open the copy's **Shell** first for the closeout run only; for the early-end and emergency runs, open it **after** Suspend, to learn whether Render still allows it.
2. Run the stop procedure (`docs/TRIAL_DEPLOYMENT.md`, section 7), with the stop-now.
3. **Record, in UTC to the second:** Suspend pressed; the stop-now asked; the `stopping now` and `stopped now` lines; **the open tab showing "Connecting"**; the tunnel Down; Render's later `stopping: asked to stop by the host` line; the route deleted.
4. **Pass:** the open tab is cut within **10 seconds** of the stop-now, and nothing restarts the copy until Resume. **If the Shell can't be opened after Suspend,** record it: the closeout (Shell opened first) must still pass, and the guide's advice to open the Shell first becomes a rule.
5. **The closed-mode proof** (the B4 gap), once, during the restart check: before resuming, keep **Alex's exact-email rule** on the Access application (the operator-only copy), set `MARGINX_TRIAL_CLOSED=1`, Resume, reconnect the route, and log in with Alex's code. **Pass:** the page says **"This MargenX trial copy is closed."**, and the browser's developer tools show the response header **`X-MargenX-Gate: closed`**. That request passed Cloudflare and was refused by MargenX itself. Also run the self-check in the Shell: it must say **closed mode**. Then finish the restart check as written (rule removed, sessions revoked, both ways back in refused), and Suspend again.

**Uploads PR:** the same three runs with a deliberately slow upload in progress: the upload can't finish being processed.

### 6. Retention and release identity
**Now (PR B):**
- **Release identity:** Render's events show the exact approved commit; the image-marker check (`docs/TRIAL_DEPLOYMENT.md`, section 6, check 1) is repeated on this commit, since the image changed (two new files).
- **Logs:** Render's logs for the whole run have no token, no `CF_Authorization`, no assertion header value, no email, no sample file names and no file contents (as B4 part 5, check 8). The stop-now and self-check print no setting.
- **Caching:** every response checked carries `Cache-Control: no-store`, and Cloudflare shows `cf-cache-status: DYNAMIC` or `BYPASS`.
- **Expected outbound traffic,** documented: cloudflared to Cloudflare; MargenX to the team's own key address (`https://margenx.cloudflareaccess.com/cdn-cgi/access/certs`), about every 5 minutes while in use, and when a token has an unknown key. Nothing else: no analytics (`gatherUsageStats` off), no error reporting.
- **Render's written answer** on what its builder keeps (build arguments, attestations) and its retention (`docs/TRIAL_DEPLOYMENT.md`, section 6, check 1). **Until it's in, real files stay off** (plan section 3.4).

**Uploads PR:** the marker tests with unique text in a made-up file's name and contents, on success, refusal and forced failure, searched across every log and diagnostic we can see; the worst-case memory with large uploads.

## How the results are recorded
One PR comment per check, in words, against the exact commit: what was done, the UTC times, pass or fail, and anything that differed. A failed check stops the run: the copy is stopped (section 7), the problem is fixed in a PR, and the affected checks run again.

## What this doesn't prove
- **Anything about uploads.** All upload parts are in the uploads PR.
- **Render's Shell after Suspend** until check 5 has measured it.
- **Other hosts or settings.** Each check holds only for the exact build and settings it ran on. A change re-runs the checks it could affect (plan section 3.5).
