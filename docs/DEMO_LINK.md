# MargenX demo link (owner guide)

The demo link shows MargenX's results for the **made-up demo sign shop**, for Abrey to show shop
owners. Decision: **D-006** in `docs/DECISIONS.md`.

## What it is

- **One static web page**, built by `scripts/build_demo_page.py` from the real MargenX code. The
  demo shop's sample files go through the same intake, profit engine and screen as the app, so the
  numbers and the look match the app.
- It is plain HTML and CSS: **no server, no script, no form, no upload of any kind.** Clicking a job
  or a customer still opens its breakdown.
- Every name and number is invented. A notice at the top says so.

## Where it lives and how to share it

- The page is published as a claude.ai artifact. Per the artifact service's documented behaviour, it
  is private until the owner shares it from the page's **Share** menu (with Abrey's email, or as a
  link). Check the sharing setting in that menu before sending the link.
- Claude Code publishes or republishes the page only when the owner asks, and never changes who can
  see it: sharing is always the owner's step.

## Updating it

After a merge that changes MargenX's screen or the demo shop files, rebuild and republish:

```
python scripts/build_demo_page.py margenx-demo.html
```

Then the owner asks Claude Code to republish that file to the same artifact. The artifact service
documents that this keeps the same link; open it afterwards to confirm the new version and the sharing.

## Rules

- Only the made-up demo shop. Never build the page from a real shop's files.
- Don't add sign-up forms, analytics, scripts or anything that collects visitors' data without a new owner decision.
- The page host (claude.ai) keeps its own access logs. That is outside the page's control.
