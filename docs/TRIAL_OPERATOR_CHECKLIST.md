# Alex's trial checklist: one shop, start to finish (DRAFT, issue #131)

**Status: a draft.** It follows the plan's go-live order (lean v1.2, section 3.5; D-008 and D-009). The invite always comes **last**. Detailed steps are in `docs/TRIAL_DEPLOYMENT.md`; the checks in `docs/TRIAL_RELEASE_CHECKS.md`. **Kept outside GitHub** (the repository is public): the shop's name, the person's email, the dates, and every record marked "private" below. On GitHub the shop is "shop A", "shop B".

## A. Before anything starts (all must be true)
- [ ] **Every release check passed** on the operator-only copy, on the exact commit this shop's copy will run, uploads included (`docs/TRIAL_RELEASE_CHECKS.md`).
- [ ] **Render's written answer** on retention and builds is in, and leaves no file-content capture unresolved (plan section 3.4).
- [ ] **The money decision is in this copy:** D-010 (decided Nov 17; built in PR #148 and #149). On this copy's commit, a made-up export with no coverage answer shows every figure as Needs a check (missing amount unknown).
- [ ] **The fit check passed** at a meeting: the owner exported the report on their own computer, following the guide; on their screen you saw the right report and settings, the customer and job on sales and job-cost lines, and the job costs they record. Nothing copied, photographed or written down. Recorded privately as "fit".
- [ ] **You told the owner** that many figures may show "Needs a check", even when the steps are followed exactly.
- [ ] **The trial terms** (final text, approved by you in writing) were accepted by the named person.
- [ ] **Your explicit yes for this shop's real data** (D-008), recorded privately.
- [ ] **The closeout** is set: the exact Miami date and time, who is responsible (you), and **Abrey as the backup**, set up in Render with the stop card below and able to open the Shell. Recorded privately. **Without this, the trial doesn't open.**

## B. Start the shop's copy, with the shop still blocked
1. [ ] A new tunnel for this copy, with its one public hostname and Protect with Access. The token is pasted into Render by you only.
2. [ ] Render: **Manual Deploy → the approved commit**, Auto-Deploy off, `MARGINX_TRIAL_INVITED_EMAIL` set to the shop person's exact email. **No Access allow rule yet.**
3. [ ] **Verify against the baseline:** the same commit, settings, host, Access application, tunnel and limits as the release run. Any difference re-runs the checks it could affect.
4. [ ] In Render's Shell: `python /app/deploy/trial/self_check.py` ends with **all refused by MargenX itself**.
5. [ ] **With the shop still blocked:** an uninvited email gets no code; then test the stop on this copy (Suspend, stop-now); then **restart it, still with no invite**, and confirm it came back with the same commit, settings and access restrictions.

## C. Open the trial
6. [ ] Record privately: the closeout date and time, who is responsible, the backup, your approval and the approved commit.
7. [ ] **Only now** add the single allow rule with the shop person's **exact** email.
8. [ ] Tell the shop its trial dates, and send the one-page guide.

## D. During the trial
- Nothing changes on the copy. No deploys. If something must change, stop first.
- **`recycled: ...` lines in Render's log are normal** (uploads PR): each one is a session ending (End session, Log out, a closed tab, a Wi-Fi drop) and MargenX starting fresh. Lines ending `every earlier login must log in again` mean MargenX ended unexpectedly or took too long: the shop sees **Log in again**. Note the time privately; if it happens more than once, ask the shop how it went.
- **If the log says `stopped: ... waiting for the host's stop`** (the tunnel stopped, or MargenX ended unexpectedly too often), the copy is down and won't come back by itself. Treat it as an early end (section E), then tell the shop. Restarting it for the same shop needs the restart check (`docs/TRIAL_DEPLOYMENT.md`, section 7, step 4) and your yes again.
- Answer questions without ever asking for a financial file.
- Hold the follow-up meeting **before** the closeout if it uses the results screen.

## E. At the closeout, an early end, or an emergency (always the same)
Open the copy's **Shell** a few minutes before a planned closeout.
1. [ ] **Render → Suspend.**
2. [ ] **Shell:** `python /app/deploy/trial/stop_now.py` (if the Shell won't open, don't wait).
3. [ ] **Cloudflare:** delete the tunnel's public hostname.
4. [ ] **Done when:** the tunnel shows Down, the log shows `stopped now` or `stopping: asked to stop by the host`, and Render shows Suspended. The routes are empty.
5. [ ] Remove the shop's email from the Access rule.
6. [ ] Revoke its Access sessions.
7. [ ] Verify the cutoff, with the restart check in closed mode (`docs/TRIAL_DEPLOYMENT.md`, section 7, step 4). End suspended, with no route.
8. [ ] Delete the copy's tunnel. Record privately what was done and when. On #131: "shop A's trial ended", with no names or figures.

---

## Abrey's stop card (the backup)
Use it only if Alex can't stop the copy at the closeout time, or Alex asks you to.
1. **Render** → the MargenX service → **Suspend**. Do this first.
2. **Render** → the same service → **Shell** → type `python /app/deploy/trial/stop_now.py` and press Enter. If the Shell won't open, skip this step.
3. **Cloudflare** → Networks → Tunnels → the copy's tunnel → **Routes** → delete the public hostname.
4. Wait until the tunnel shows **Down**, then tell Alex what you did and the times.

Never press Resume, Restart or Deploy. Never add anyone to the Access rule.
