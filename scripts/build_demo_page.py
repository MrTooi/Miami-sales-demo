"""Build the MargenX demo page: one static HTML file of the made-up demo sign shop (D-006).

The page is what the public demo link shows. It is built from the real MargenX code, so its numbers
and look always match the app: the demo shop's sample files go through the same intake and profit
engine (job_intake, job_profit), the same summary (marginx_insights), and the same screen
(marginx_ui). It is plain HTML and CSS: no server, no script, no form and no way to upload anything.
Clicking a job or a customer still opens its breakdown (HTML details elements).

Usage: python scripts/build_demo_page.py OUTPUT.html
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import job_intake as ji  # noqa: E402
import job_profit as jp  # noqa: E402
import marginx_insights as mi  # noqa: E402
import marginx_ui as ui  # noqa: E402

SAMPLES = ROOT / "sample_data" / "marginx"
DEMO_FILES = {"invoices": "demo_sign_shop_invoices.csv", "costs": "demo_sign_shop_costs.csv"}
TITLE = "MargenX Demo Shop"
NOTICE = ("Online demo with a made-up sign shop. Every name and number here is invented. "
          "To see your own jobs, ask us about early access.")

# The page's own layout around the app's styles: a centred column with a safe side gutter on phones.
PAGE_CSS = """
<style>
body{margin:0;background:#E6F6EE;color:#0E241B;padding-left:max(16px, env(safe-area-inset-left, 0px));
padding-right:max(16px, env(safe-area-inset-right, 0px))}
.mx-page{max-width:1080px;margin:0 auto;padding-block:32px 48px;display:flex;flex-direction:column;gap:0}
.mx-notice{background:#E8F1F9;color:#1E5C8C;border-radius:14px;padding:14px 18px;font-size:.95rem;line-height:1.5;margin:6px 0 22px}
.mx-notice b{color:#174A72}
.mx-cta{margin-top:8px;background:#0F7A55;color:#F4FBF7;border-radius:18px;padding:22px 26px;display:flex;flex-direction:column;gap:6px}
.mx-cta .h{font-family:'Plus Jakarta Sans','Inter',system-ui,sans-serif;font-weight:800;font-size:1.3rem;color:#FFFFFF}
.mx-cta .d{font-size:.95rem;color:#DDF3E9;line-height:1.5}
.mx-notes{font-size:.82rem;color:#5A6F66;margin:-6px 2px 18px;display:flex;flex-direction:column;gap:6px}
summary:focus-visible{outline:2px solid #0F7A55;outline-offset:2px;border-radius:10px}
</style>
"""


def demo_report() -> jp.ProfitReport:
    """The demo shop through the same intake and engine as the app, with every automatic choice."""
    results = {}
    for kind, name in DEMO_FILES.items():
        headers, records = ji.read_csv((SAMPLES / name).read_bytes())
        mapping = ji.suggest_mapping(headers, kind)
        date_format = ji.suggest_date_format(ji.column_values(headers, records, mapping["date"])) or "MM/DD/YYYY"
        results[kind] = ji.intake(headers, records, mapping, kind, date_format)
        if results[kind].rejected:
            raise SystemExit(f"{name} has rows that couldn't be read; the demo shop should have none.")
    return jp.job_profit(results["invoices"], results["costs"])


def _render(fn, *args) -> str:
    """Collect what a marginx_ui function would put on the page, as one string."""
    out: list[str] = []
    original = ui._html
    ui._html = lambda markup: out.append(re.sub(r"[\r\n]+", " ", markup))
    try:
        fn(*args)
    finally:
        ui._html = original
    return "".join(out)


def build_page() -> str:
    report = demo_report()
    summary = mi.summarize(report)
    header = _render(ui.header, False)
    results = _render(ui.results, report, summary, mi.attention(report), mi.period_text(report))
    # Notes shown under the results in the app (the overhead note is already the "after overhead" line).
    notes = "".join(f"<div>{escape(n)}</div>" for n in report.notes if "overhead or fee line" not in n)
    notes_html = f'<div class="mx-notes">{notes}</div>' if notes else ""
    head, rest = NOTICE.split(". ", 1)
    return (
        f"<title>{escape(TITLE)}</title>\n"
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        f"{ui._CSS}{PAGE_CSS}"
        '<main class="mx-page">'
        f"{header}"
        f'<div class="mx-notice"><b>{escape(head)}.</b> {escape(rest)}</div>'
        f"{results}{notes_html}"
        '<div class="mx-cta"><div class="h">Try it early, at no cost</div>'
        '<div class="d">One hour with your own sales and cost reports. We’re inviting a few Miami shops first.</div></div>'
        "</main>\n"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    Path(argv[1]).write_text(build_page(), encoding="utf-8")
    print(f"wrote {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
