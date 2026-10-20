# MargenX pilot visit checklist (sit-down pilot)

**Use this only after the owner has approved real data for a named pilot shop in a written decision (D-007 or later; D-006 is the public demo link, which takes no files).** Until then, use the made-up sample files only. Merging step 3 doesn't approve real data by itself (D-003).

How the pilot works: Alex or Abrey visits the shop and runs MargenX on a team laptop, with the shop owner present. The shop's files are read in memory only. They are never saved, uploaded or kept after the session.

## Before the visit (on the team laptop)
- [ ] **Disk encryption is on:** FileVault on a Mac, BitLocker on Windows.
- [ ] **The laptop has a password and locks** after a few minutes idle.
- [ ] **Latest MargenX:** in the project folder, run `git pull`.
- [ ] **No screen recording, screen sharing or remote-control apps** are running.
- [ ] **No tunnel or proxy is running** (e.g. ngrok, Cloudflare Tunnel, Tailscale Funnel, a VPN "share" feature). MargenX refuses requests that show signs of a proxy or tunnel, but it can't detect every one.
- [ ] **Practice once with the sample files** so the visit goes quickly.

## Starting MargenX in pilot mode
Run this in the project folder.

Mac:
```bash
MARGINX_PILOT=1 streamlit run marginx_pilot.py --server.address localhost
```

Windows (PowerShell):
```powershell
$env:MARGINX_PILOT="1"; streamlit run marginx_pilot.py --server.address localhost
```

`marginx_pilot.py` opens **only** the MargenX page. (`app.py` now opens the same single page. The older Ledger screen, which kept imports in a file on the laptop, was retired on 2026-10-20.) Never upload a shop's files anywhere else.

The page must say **"Pilot session on this laptop"**. If it says "made-up data only", pilot mode isn't on: stop, don't use real files, and check the command.

Pilot mode only works with `--server.address localhost`, opened in a browser on this same laptop at `http://localhost:8501`. This keeps other computers from reaching the app. Never run pilot mode on a shared or public server.

## During the visit
1. **Explain what happens.** Use the agreement text on the screen: we read their files on this laptop only, nothing is kept, and they can stop at any time.
2. **The shop owner exports the files** from QuickBooks/Square while you watch: sales/invoices and costs/bills, as CSV.
3. **Move the files to the laptop with a USB drive or AirDrop.** Don't email them, and don't put them in Google Drive, Dropbox or a chat app.
4. **The owner ticks the agreement box themselves.** Then upload the files.
5. **Look at the results together.** Write down what they say in the #30 format, in their own words. **Never copy their numbers, customer names or job details into notes.** Write "a customer job lost money on materials", not "Acme lost $412".
6. **No screenshots or photos of the screen.**

## Before you leave (don't skip this)
- [ ] Click **End session and clear everything** in MargenX. It should say the uploaded files "were removed from MargenX's upload storage". If it says it **couldn't confirm** that, go straight to the next step. End session only clears what MargenX holds: it does **not** delete the original CSV files on the laptop.
- [ ] Close the browser tab, then stop MargenX: press Ctrl+C in the terminal and close the terminal. Error details can appear there.
- [ ] **Delete the shop's files from the laptop.** Check Downloads, the Desktop and wherever AirDrop saved them. **Then empty the Trash/Recycle Bin.**
- [ ] **Delete the files from the USB drive**, or give the drive to the owner.
- [ ] Ask the owner whether they want the exported files deleted from **their** computer too.
- [ ] Note the date, the shop (by type, e.g. "sign shop A") and that the deletion was done, without any of their figures.

## Before the first real visit, and after any Streamlit upgrade
Repeat the real upload-and-delete test with a **made-up** CSV. MargenX's cleanup relies on Streamlit 1.65.0 internals (`pilot_safety.release_uploads`).
1. Start pilot mode and tick the agreement.
2. Upload the made-up CSV and check that its line is read.
3. Click **End session**. It must show the "removed from MargenX's upload storage" message, and the file name and results must be gone.
4. Run the test suite (`python -m unittest discover -s tests`). It must pass.

## If something goes wrong
- **The page shows an error:** click End session and start again. Don't screenshot it. Write down what you were doing, not the data.
- **A file was emailed or uploaded somewhere by mistake:** tell Alex the same day. Delete it there, and tell the shop owner honestly.
- **The owner wants to stop:** click End session right away and delete the files.

## What this setup does and doesn't protect
- **It does:**
  - Files stay on one laptop and in memory only.
  - Nothing is saved by MargenX. **End session** removes the uploaded files from MargenX's upload storage, clears the answers and results, and checks the files are gone before saying so. It can't prove that no copy remains anywhere in the computer's memory, which is why the tab is closed and MargenX stopped at the end of every visit (stopping MargenX drops everything). A closed tab's files are dropped within about 10 seconds.
  - No usage data is sent anywhere.
  - Error pages show no file contents.
  - Real files are refused unless pilot mode is on, the app listens on this computer only, and the browser visit itself looks local (no proxy or tunnel signs).
  - The upload area doesn't appear until the shop owner ticks the agreement.
- **It doesn't:**
  - It doesn't protect files the laptop itself kept: Downloads, Trash, AirDrop, the USB drive. That's what the deletion steps are for.
  - It doesn't protect the laptop if it's lost while unlocked.
  - It can't detect every tunnel or remote-access tool. That's why none may be running during a visit.
  - It doesn't make MargenX's figures certain. "Provisional" results must be explained as provisional.
