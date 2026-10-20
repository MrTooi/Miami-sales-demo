# MargenX demo link: how to put it online (owner steps)

The demo link lets anyone with the link click around the **made-up demo sign shop**. It is
for Abrey to show shop owners. Decision: **D-006** in `docs/DECISIONS.md`.

## What the demo link is, and isn't

- It runs `margenx_demo.py`, which shows **only the made-up demo shop**.
- It has **no upload box**, no file choice and no pilot mode, so no real file can ever be put into it.
- Every name and number is invented. A notice at the top says so.
- It is **public to anyone who has the link**. That's fine because it holds no real data.

## Put it online (about 5 minutes, done by the owner)

Claude Code never deploys. These steps use your own accounts.

1. Go to **share.streamlit.io** and sign in with **GitHub** (the MrTooi account).
2. Click **Create app**, then choose **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `MrTooi/Miami-sales-demo`
   - **Branch:** `main`
   - **Main file path:** `margenx_demo.py` ← **must be exactly this file.** Never `app.py` or `marginx_pilot.py`, which have upload boxes.
   - **App URL:** pick a name, for example `margenx-demo` (giving `margenx-demo.streamlit.app`).
4. Open **Advanced settings** and choose **Python 3.11**. Leave Secrets empty.
5. Click **Deploy**. The first start takes a few minutes.
6. Open the link and check: the blue notice "Online demo with a made-up sign shop" is at the top, and **there is no upload box anywhere**. Then send the link to Abrey.

## Updating and taking it down

- The link follows the `main` branch: once a pull request is merged, the demo updates by itself.
- To take it down: on share.streamlit.io, open the app's **⋮** menu and choose **Delete**.

## Rules

- Only ever deploy `margenx_demo.py`. Real shop files are used only in the sit-down pilot on the
  team laptop (`marginx_pilot.py`, `docs/PILOT_VISIT_CHECKLIST.md`), after the owner's separate
  real-data decision.
- Don't add our own sign-up forms, analytics or anything that collects visitors' data without a new owner decision.
- MargenX itself sends no usage statistics (`gatherUsageStats = false` in `.streamlit/config.toml`). The hosting
  service keeps its own logs and shows the owner basic viewer counts; that is outside the app's control and is
  covered by Streamlit's own privacy policy. Read it before publishing if that matters to you.
