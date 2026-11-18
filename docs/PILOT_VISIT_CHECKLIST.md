# MargenX pilot visit checklist (sit-down pilot)

**Use this only after the owner has approved real data for a named pilot shop in a written decision (D-008 or later; D-006 is the public demo page and D-007 the wider target customer, and neither approves any files).** Until then, use the made-up sample files only. Merging step 3 doesn't approve real data by itself (D-003).

How the pilot works: Alex or Abrey visits the shop and runs MargenX on a team laptop, with the shop owner present. The shop's files are read in memory only. They are never saved, uploaded or kept after the session.

**This checklist is how we keep the promises in the signed MargenX Free Pilot Agreement and Privacy Notice** (draft kept as a Claude Doc; the owner fills in the blanks before first use). If a step here can't be done, don't run the pilot: the agreement says we do it. A signed agreement doesn't approve real data by itself; the real-data decision above still comes first.

## Before the visit (on the team laptop)
- [ ] **Disk encryption is on:** FileVault on a Mac, BitLocker on Windows.
- [ ] **The laptop has a password and locks** after a few minutes idle.
- [ ] **Find My (Mac) or Find my device (Windows) is turned on**, so a lost laptop can be located and locked (on a Mac, also erased).
- [ ] **Latest MargenX:** in the project folder, run `git pull`.
- [ ] **No screen recording, screen sharing or remote-control apps** are running.
- [ ] **Cloud syncing is off for the folders files may land in** (Downloads, Desktop, Documents): iCloud Drive "Desktop & Documents", Dropbox, Google Drive, OneDrive. The agreement promises shop files aren't sent to any cloud service.
- [ ] **Automatic backups are paused for the visit** (Time Machine or similar), so no backup copy of the shop's files is made.
- [ ] **Printed copies ready:** two copies of the signed-version Free Pilot Agreement (one for the owner, one for us) and the Privacy Notice for the owner to keep.
- [ ] **No tunnel or proxy is running** (e.g. ngrok, Cloudflare Tunnel, Tailscale Funnel, a VPN "share" feature). MargenX refuses requests that show signs of a proxy or tunnel, but it can't detect every one.
- [ ] **Practice once with made-up files** so the visit goes quickly:
  - the sample CSV files, for a shop that doesn't use QuickBooks Online;
  - for a QuickBooks Online shop, a Profit and Loss Detail and a Sales by Customer Detail exported from **QuickBooks' own practice company**, which holds made-up data. Answer every question MargenX asks, so you know what the owner will see.

## Starting MargenX in pilot mode
**Easiest on the Mac:** double-click **Start MargenX** on the Desktop (a copy of `scripts/start_margenx.command`). It asks GitHub which version is approved (the tip of `main` at `https://github.com/MrTooi/Miami-sales-demo`), so it **needs the internet** (a phone hotspot is fine); it never takes that from the project folder's settings. It runs MargenX from its own copy in `~/MargenX-app`, never from the project folder, and starts only when every file in that copy matches the approved version byte for byte, with nothing added. It uses only this Mac's own system programs, and git runs with its features that could run another program switched off. It then checks the Python setup, starts pilot mode on this laptop only and opens `http://localhost:8501`. If anything isn't right it says what and doesn't start. Close its Terminal window to stop MargenX.

Or run this in the project folder, checked out on `main`.

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
1. **Sign the agreement first, before any files.** Walk through it in plain words, especially: what MargenX shows (job contribution, not net profit), how files are handled and cleaned up, that it isn't advice, and the limit of responsibility. Both of you sign and date both copies; the owner keeps one, with the Privacy Notice.
2. **Explain what happens on screen.** Use the agreement text on the screen too: we read their files on this laptop only, nothing is kept, and they can stop at any time.
3. **Ask for files without sensitive details.** Before exporting, ask the owner to leave out Social Security numbers, card numbers, bank logins and other personal details. If a file has them, don't use it: ask for a clean version that still has every sale or cost row. **Never run with only part of what MargenX needs** (see step 4): if a clean version isn't possible, stop the pilot rather than show results with something missing.
4. **The shop owner exports the files on their own computer while you watch.** Which files depends on how they keep their books:
   - **QuickBooks Online (the usual case):**
     1. **Reports** → **Profit and Loss Detail**. Choose the dates to look at, for example last quarter, and **Accounting method: Accrual**. Cash basis is refused.
     2. **No filters, and no changed columns.** Leave every customer and every account in. A filter doesn't show in the file, so MargenX can't see it, and it can make jobs look more profitable than they are.
     3. **Export** → **Export to Excel**.
     4. **Sales by Customer Detail for the same dates**, exported the same way. MargenX uses it only to double-check the sales. Without it, profit by job can't be Complete.

     The menu names are still to be confirmed against a real QuickBooks Online account; correct them here if they differ. A Profit and Loss Detail already holds the sales and the costs, so don't add other sales or cost files with it.
   - **Other systems (for example Square):** the sales or invoices file and the costs or bills file, as CSV.
5. **Move the files to the laptop with a USB drive or AirDrop.** Don't email them, and don't put them in Google Drive, Dropbox or a chat app.
6. **Never put a shop's file, numbers or screen into any AI tool** (ChatGPT, Claude, Copilot or similar) or any website. We only open their files in MargenX on the laptop, and never upload or send them anywhere.
7. **The owner ticks the agreement box themselves.** Then upload the files.
8. **The owner answers MargenX's questions themselves.** You can read a question out and explain the words, but the answer is theirs: it's about their books, and MargenX relies on it.
   - **For a QuickBooks report, MargenX lists the cost accounts it found, with their totals, and asks whether the file includes the whole business, with no filters.** The owner chooses **Yes, I checked** only after checking that list against QuickBooks and their export settings. **No, something is missing** and **Not sure** are fine answers. Until the answer is "Yes, I checked", every figure says **Needs a check (missing amount unknown)**.
   - **Never nudge the owner toward "Yes" to make a figure Complete.** A Complete figure built on a guessed answer is exactly what MargenX exists to avoid.
9. **Look at the results together.** Write down what they say in the #30 format, in their own words. **Never copy their numbers, customer names or job details into notes.** Write "a customer job lost money on materials", not "Acme lost $412".
   - **Explain "Needs a check" plainly:** MargenX couldn't prove that figure from the file and the answers, and it says why. That's the product working, not a fault.
10. **No screenshots or photos of the screen,** and no recording of the session.

## Before you leave (don't skip this)
- [ ] Click **End session and clear everything** in MargenX. It should say the uploaded files "were removed from MargenX's upload storage". If it says it **couldn't confirm** that, go straight to the next step. End session only clears what MargenX holds: it does **not** delete the original exported files (CSV or Excel) on the laptop.
- [ ] Close the browser tab, then stop MargenX: press Ctrl+C in the terminal and close the terminal. Error details can appear there.
- [ ] **Delete the shop's files from the laptop.** Check Downloads, the Desktop and wherever AirDrop saved them. **Then empty the Trash/Recycle Bin.**
- [ ] **Delete the files from the USB drive**, or give the drive to the owner.
- [ ] Ask the owner whether they want the exported files deleted from **their** computer too.
- [ ] If the owner asks, **explain the cleanup steps you just took** (the agreement promises this).
- [ ] Note the date, the shop (by type, e.g. "sign shop A") and that the deletion was done, without any of their figures.
- [ ] **Turn cloud syncing and automatic backups back on** only after the files are deleted and the Trash is emptied.
- [ ] **File the signed agreement** where the Privacy Notice says signed agreements are kept.

## Before the first real visit, and after any Streamlit upgrade
Repeat the real upload-and-delete test with a **made-up** CSV, and again with a **made-up** QuickBooks Profit and Loss Detail (from QuickBooks' practice company). MargenX's cleanup relies on Streamlit 1.65.0 internals (`pilot_safety.release_uploads`).
1. Start pilot mode and tick the agreement.
2. Upload the made-up file and check that it is read: the CSV's line, or the Profit and Loss Detail's questions and results.
3. Click **End session**. It must show the "removed from MargenX's upload storage" message, and the file name and results must be gone.
4. Run the test suite (`python -m unittest discover -s tests`). It must pass.

## If something goes wrong
- **The page shows an error:** click End session and start again. Don't screenshot it. Write down what you were doing, not the data.
- **A file was emailed, synced or uploaded somewhere by mistake:** tell Alex the same day. Contain it straight away: delete it there, or ask the service to delete it. **Tell the shop owner without undue delay, without waiting for the deletion to be confirmed:** what happened, what we've done so far, and anything they should do (agreement section 4). Write down what happened, when and what was done, without their figures. Alex checks whether a breach-notice law applies (for example Florida's, if personal information was involved).
- **The laptop is lost or stolen with a shop's files on it:** tell Alex immediately, and **tell the shop owner right away as above; don't wait for the laptop to be found, locked or erased.** Then:
  - **Mac:** if Find My was turned on before the visit, use it (icloud.com/find) to lock the laptop and erase it remotely.
  - **Windows:** Find my device can only locate and lock the laptop, not erase it. Use it to lock it.
  - Change the passwords for the laptop's account and any accounts signed in on it.
  - Disk encryption (see "Before the visit") is what protects the files on a lost laptop; remote locking or erasing only works if the laptop goes online.
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
  - It doesn't make MargenX's figures certain. Figures marked **Needs a check** (or "provisional", for CSV files) must be explained as not proven. A **Complete** QuickBooks figure also relies on the owner's own answers, such as "Yes, I checked".
