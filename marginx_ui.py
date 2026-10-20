"""MarginX look and feel: brand styles and the HTML for the results screen.

Light, calm and plain-spoken, matching the website: mint background, white cards, dark-green
accents. Every value that can come from a shop's file (customer names, job descriptions,
reasons) is HTML-escaped here before it reaches the page.
"""
from __future__ import annotations

from html import escape

import streamlit as st

from job_profit import CATEGORIES, CATEGORY_LABELS, ProfitReport
from marginx_insights import Insight, Summary, money, percent, pricing

BRAND = "MarginX"  # the product name, in one place
TAGLINE = "Profit per job for print, sign and apparel shops"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
:root{--mx-green:#0F7A55;--mx-green-dark:#0B5C40;--mx-mint:#E6F6EE;--mx-mint-2:#F4FBF7;--mx-ink:#0E241B;
--mx-muted:#5A6F66;--mx-line:#DCEDE5;--mx-card:#FFFFFF;--mx-red:#B42318;--mx-red-bg:#FDECEA;--mx-amber:#9A5B05;
--mx-amber-bg:#FEF4E2;--mx-blue:#1E5C8C;--mx-blue-bg:#E8F1F9}
html,body,[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,var(--mx-mint) 0%,var(--mx-mint-2) 420px)!important;color:var(--mx-ink)}
[data-testid="stHeader"]{background:transparent!important}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"]{display:none!important}
[data-testid="stAppViewContainer"] *{font-family:'Inter',system-ui,sans-serif}
[data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded'!important}
.block-container{max-width:1080px;padding-top:2.2rem;padding-bottom:4rem}
h1,h2,h3,.mx-h{font-family:'Plus Jakarta Sans','Inter',sans-serif!important;color:var(--mx-ink)!important;letter-spacing:-.02em}
.mx-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px}
.mx-brand{display:flex;align-items:center;gap:10px;font-family:'Plus Jakarta Sans',sans-serif;font-weight:800;font-size:1.25rem;color:var(--mx-ink)}
.mx-brand b{color:var(--mx-green)}
.mx-mark{width:34px;height:34px;border-radius:10px;background:var(--mx-green);display:flex;align-items:center;justify-content:center}
.mx-pill{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:600;padding:5px 11px;border-radius:999px;background:var(--mx-amber-bg);color:var(--mx-amber)}
.mx-pill.pilot{background:var(--mx-blue-bg);color:var(--mx-blue)}
.mx-steps{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 22px}
.mx-step{font-size:.85rem;padding:7px 13px;border-radius:999px;background:rgba(255,255,255,.55);color:var(--mx-muted);border:1px solid var(--mx-line)}
.mx-step.on{background:var(--mx-green);color:#fff;border-color:var(--mx-green);font-weight:600}
.mx-step.done{color:var(--mx-green);font-weight:600}
.mx-kicker{color:var(--mx-muted);font-size:.9rem;margin:2px 0 4px}
.mx-title{font-family:'Plus Jakarta Sans',sans-serif;font-weight:800;font-size:2.05rem;line-height:1.12;letter-spacing:-.03em;margin:0 0 18px;color:var(--mx-ink)}
.mx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.mx-metric{background:var(--mx-card);border:1px solid var(--mx-line);border-radius:16px;padding:16px 18px;box-shadow:0 1px 2px rgba(14,36,27,.04)}
.mx-metric .l{font-size:.82rem;color:var(--mx-muted);font-weight:500}
.mx-metric .v{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.65rem;font-weight:800;letter-spacing:-.02em;margin-top:4px;color:var(--mx-ink)}
.mx-metric .s{font-size:.8rem;color:var(--mx-muted);margin-top:2px}
.mx-metric .v.red{color:var(--mx-red)}.mx-metric .v.amber{color:var(--mx-amber)}.mx-metric .v.green{color:var(--mx-green)}
.mx-card{background:var(--mx-card);border:1px solid var(--mx-line);border-radius:18px;padding:18px 22px;margin-bottom:16px;box-shadow:0 1px 2px rgba(14,36,27,.04)}
.mx-card h3{font-size:1.05rem!important;margin:0 0 10px!important;font-weight:700}
.mx-item{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-top:1px solid var(--mx-line)}
.mx-item:first-of-type{border-top:0}
.mx-ico{flex:0 0 30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.95rem}
.mx-ico.loss{background:var(--mx-red-bg);color:var(--mx-red)}.mx-ico.warn{background:var(--mx-amber-bg);color:var(--mx-amber)}.mx-ico.info{background:var(--mx-blue-bg);color:var(--mx-blue)}
.mx-item .t{font-weight:600;color:var(--mx-ink)}.mx-item .d{font-size:.88rem;color:var(--mx-muted);margin-top:2px}
.mx-row{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,2fr) 128px;gap:14px;align-items:center;padding:10px 0;border-top:1px solid var(--mx-line)}
.mx-row:first-of-type{border-top:0}
.mx-row .n{font-weight:600}.mx-row .n small{display:block;font-weight:400;color:var(--mx-muted);font-size:.8rem}
.mx-bar{height:7px;background:#EEF5F1;border-radius:6px;overflow:hidden;margin:3px 0}
.mx-bar i{display:block;height:7px;border-radius:6px}
.mx-bar i.sales{background:#A7E3C8}.mx-bar i.left{background:var(--mx-green)}.mx-bar i.neg{background:var(--mx-red)}
.mx-row .r{text-align:right}.mx-row .r .a{font-weight:700;font-family:'Plus Jakarta Sans',sans-serif}.mx-row .r .p{font-size:.8rem;color:var(--mx-muted)}
.mx-job{display:grid;grid-template-columns:12px minmax(0,1fr) auto 120px;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--mx-line);font-size:.95rem}
.mx-job:first-of-type{border-top:0}
.mx-dot{width:10px;height:10px;border-radius:50%}.mx-dot.complete{background:var(--mx-green)}.mx-dot.loss{background:var(--mx-red)}.mx-dot.provisional{background:#E0A43A}.mx-dot.unavailable{background:#B7C4BE}
.mx-job .w small{color:var(--mx-muted);font-size:.82rem}
.mx-tag{font-size:.75rem;padding:3px 9px;border-radius:999px;white-space:nowrap}
.mx-tag.complete{background:var(--mx-mint);color:var(--mx-green-dark)}.mx-tag.provisional{background:var(--mx-amber-bg);color:var(--mx-amber)}.mx-tag.unavailable{background:#EEF2F0;color:var(--mx-muted)}
.mx-job .a{text-align:right;font-weight:700;font-family:'Plus Jakarta Sans',sans-serif}.mx-job .a.neg{color:var(--mx-red)}
.mx-after{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#fff;border:1px dashed #BFE3D2;border-radius:14px;padding:12px 18px;margin:-4px 0 18px;font-size:.9rem;color:var(--mx-muted)}
.mx-after b{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.15rem;color:var(--mx-ink)}
details.mx-d{border-top:1px solid var(--mx-line)}details.mx-d:first-of-type{border-top:0}
details.mx-d>summary{list-style:none;cursor:pointer}details.mx-d>summary::-webkit-details-marker{display:none}
details.mx-d>summary .mx-job,details.mx-d>summary .mx-row{border-top:0}
details.mx-d>summary:hover{background:#F6FBF8;border-radius:10px}
.mx-chev{color:var(--mx-muted);font-size:.8rem;margin-left:4px}
details[open] .mx-chev{display:inline-block;transform:rotate(90deg)}
.mx-break{margin:0 0 12px 24px;padding:12px 16px;background:#F6FBF8;border-radius:12px;font-size:.88rem}
.mx-break table{width:100%;border-collapse:collapse;border:0!important;margin:0}
.mx-break tr,.mx-break td{border:0!important;background:transparent!important}.mx-break td{padding:3px 0!important;font-size:.88rem}.mx-break td.r{text-align:right;font-variant-numeric:tabular-nums}
.mx-break tr.tot td{border-top:1px solid var(--mx-line);font-weight:700;padding-top:6px}
.mx-break .why{color:var(--mx-amber);margin-top:8px}.mx-break .price{color:var(--mx-green-dark);margin-top:8px}
.mx-job .a .p{display:block;font-size:.75rem;font-weight:500;color:var(--mx-muted);font-family:'Inter',sans-serif}
.mx-legend{font-size:.78rem;color:var(--mx-muted);margin-top:8px}
.mx-legend span{display:inline-block;width:12px;height:7px;border-radius:3px;margin:0 5px 1px 0;vertical-align:middle}
.mx-foot{font-size:.82rem;color:var(--mx-muted);margin:4px 2px 18px}
.mx-file{font-family:'Plus Jakarta Sans',sans-serif;font-weight:700;font-size:1rem;margin:14px 0 2px;color:var(--mx-ink)}
.mx-section{font-family:'Plus Jakarta Sans',sans-serif;font-weight:800;font-size:1.25rem;margin:26px 0 6px;color:var(--mx-ink)}
div.stButton>button{border-radius:11px!important;border:1px solid var(--mx-line)!important;background:#fff!important;color:var(--mx-ink)!important;font-weight:600!important}
div.stButton>button:hover{border-color:var(--mx-green)!important;color:var(--mx-green)!important}
div[data-testid="stExpander"]{border:1px solid var(--mx-line)!important;border-radius:14px!important;background:rgba(255,255,255,.7)!important}
[data-testid="stDataFrame"]{border:1px solid var(--mx-line);border-radius:12px;overflow:hidden}
.stAlert{border-radius:14px!important}
div[data-testid="stAlertContentWarning"]{font-size:.88rem}
@media(max-width:700px){.mx-title{font-size:1.6rem}.mx-metric{padding:12px 14px}.mx-metric .v{font-size:1.3rem}.mx-row{grid-template-columns:minmax(0,1fr) 110px}.mx-row .bars{display:none}
.mx-job{grid-template-columns:12px minmax(0,1fr) 96px}.mx-job .tagc{display:none}}
</style>
"""

_MARK = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
         '<path d="M3 8l9-4 9 4-9 4-9-4z" fill="#A7E3C8"/><path d="M3 12l9 4 9-4" stroke="#fff" stroke-width="1.8" '
         'stroke-linejoin="round"/><path d="M3 16l9 4 9-4" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>')


def apply_brand() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def header(pilot: bool) -> None:
    pill = ('<span class="mx-pill pilot">Pilot session · this laptop only</span>' if pilot
            else '<span class="mx-pill">Example data only</span>')
    name = escape(BRAND)
    brand = f"<span>{name[:-1]}<b>{name[-1]}</b></span>" if name.endswith("X") else f"<span>{name}</span>"
    _html(f'<div class="mx-top"><div class="mx-brand"><div class="mx-mark">{_MARK}</div>{brand}</div>{pill}</div>'
          f'<div class="mx-kicker">{escape(TAGLINE)}</div>')


def steps(current: int) -> None:
    """The three steps, with the current one highlighted (1 add files, 2 answer questions, 3 results)."""
    labels = ("1  Add your files", "2  Answer a few questions", "3  See where your money is made")
    parts = []
    for n, label in enumerate(labels, start=1):
        state = "on" if n == current else ("done" if n < current else "")
        mark = "✓ " if n < current else ""
        parts.append(f'<span class="mx-step {state}">{mark}{escape(label)}</span>')
    _html(f'<div class="mx-steps">{"".join(parts)}</div>')


def section(title: str) -> None:
    _html(f'<div class="mx-section">{escape(title)}</div>')


def file_title(name: str) -> None:
    _html(f'<div class="mx-file">{escape(name)}</div>')


def _money(amount) -> str:
    return escape(money(amount))


def results(report: ProfitReport, summary: Summary, items: list[Insight], period: str) -> None:
    """The results screen: headline, key numbers, what needs attention, customers and jobs."""
    _html(f'<div class="mx-kicker">{escape(period)}</div><div class="mx-title">Here\'s where your money was made</div>')

    left_note = (f"{summary.share_percent}% of sales on jobs with a figure" if summary.share_percent is not None else "")
    if summary.figure_is_provisional:
        left_note += " · includes jobs that need a check"
    losing_class = "red" if summary.losing_jobs else "green"
    check_class = "amber" if summary.jobs_to_check else "green"
    metrics = [
        ("Sales", _money(summary.sales), f"{summary.jobs} jobs"),
        ("Left after job costs", _money(summary.left_after_job_costs), escape(left_note), ""),
        ("Jobs losing money", f"{summary.losing_jobs} of {summary.jobs}", "", losing_class),
        ("Jobs that need a check", str(summary.jobs_to_check), "missing costs or figures" if summary.jobs_to_check
         else "all jobs complete", check_class),
    ]
    cards = []
    for m in metrics:
        label, value, sub = m[0], m[1], m[2]
        cls = m[3] if len(m) > 3 else ""
        cards.append(f'<div class="mx-metric"><div class="l">{escape(label)}</div><div class="v {cls}">{value}</div>'
                     f'<div class="s">{sub}</div></div>')
    _html(f'<div class="mx-grid">{"".join(cards)}</div>')
    if summary.unlinked_costs:
        _html(f'<div class="mx-after"><div>After the {_money(summary.unlinked_costs)} of costs not tied to any job '
              f'(rent and other overhead), these files leave <b>{_money(summary.after_unlinked_costs)}</b></div>'
              f'<div style="font-size:.8rem;max-width:300px;text-align:right">Your real profit only if these files '
              f'include all your costs for the period.</div></div>')

    if items:
        icons = {"loss": "↓", "warn": "!", "info": "i"}
        rows = "".join(f'<div class="mx-item"><div class="mx-ico {i.level}">{icons[i.level]}</div><div>'
                       f'<div class="t">{escape(i.title)}</div><div class="d">{escape(i.detail)}</div></div></div>'
                       for i in items)
        foot = ""
        if summary.usual_margin is not None and any("usual" in i.detail for i in items):
            foot = (f'<div class="mx-legend">Your usual margin ({percent(summary.usual_margin, 1)}%) is the average of '
                    "your jobs with complete costs.</div>")
        _html(f'<div class="mx-card"><h3>What needs your attention</h3>{rows}{foot}</div>')
    else:
        _html('<div class="mx-card"><h3>What needs your attention</h3><div class="mx-item"><div class="mx-ico info">✓</div>'
              '<div><div class="t">Nothing stands out</div><div class="d">No job lost money and every figure is complete.'
              '</div></div></div></div>')

    _customers(report)
    _jobs(report, summary)


def _customers(report: ProfitReport) -> None:
    counted = [c for c in report.customers if c.contribution is not None]
    if not counted:
        return
    top = max(max(c.sales for c in counted), 1)
    rows = []
    for c in sorted(counted, key=lambda c: (-c.contribution, c.customer)):
        share = percent(c.contribution, c.sales)  # the same rounding as the attention list
        left_width = max(0, min(100, int(c.contribution * 100 / top)))
        bar = "neg" if c.contribution < 0 else "left"
        note = "" if c.status == "complete" else "<small>Needs a check</small>"
        jobs = [j for j in report.jobs if j.job_id in c.jobs]
        inner = "".join(f'<tr><td>{escape(j.description or "Job")} · {escape(j.job_id)}</td>'
                        f'<td class="r">{"—" if j.contribution is None else _money(j.contribution)}</td></tr>'
                        for j in jobs)
        why = f'<div class="why">{escape(" ".join(c.reasons))}</div>' if c.reasons else ""
        rows.append(
            f'<details class="mx-d"><summary><div class="mx-row"><div class="n">{escape(c.customer)}'
            f'<span class="mx-chev">›</span>{note}</div>'
            f'<div class="bars"><div class="mx-bar"><i class="sales" style="width:{int(c.sales * 100 / top)}%"></i></div>'
            f'<div class="mx-bar"><i class="{bar}" style="width:{left_width}%"></i></div></div>'
            f'<div class="r"><div class="a">{_money(c.contribution)}</div>'
            f'<div class="p">{"" if share is None else f"{share}% of "}{_money(c.sales)}</div></div></div></summary>'
            f'<div class="mx-break"><table>{inner}</table>{why}</div></details>')
    legend = ('<div class="mx-legend"><span style="background:#A7E3C8"></span>Sales'
              '<span style="background:#0F7A55;margin-left:14px"></span>Left after job costs</div>')
    _html(f'<div class="mx-card"><h3>Customers, by what they leave you</h3>{"".join(rows)}{legend}</div>')


def _jobs(report: ProfitReport, summary: Summary) -> None:
    tag = {"complete": "Complete", "provisional": "Needs a check", "unavailable": "No figure yet"}
    order = {"complete": 0, "provisional": 1, "unavailable": 2}
    jobs = sorted(report.jobs, key=lambda j: (j.contribution is None, -(j.contribution or 0), order[j.status], j.job_id))
    rows = []
    for j in jobs:
        what = escape(j.description or "Job")
        who = escape(", ".join(j.customers) or "No customer")
        amount = "—" if j.contribution is None else _money(j.contribution)
        neg = " neg" if j.contribution is not None and j.contribution < 0 else ""
        share = percent(j.contribution, j.sales) if j.contribution is not None else None
        # A job that needs a check may be missing costs: its margin is shown as "so far", not as fact.
        share_html = (f'<span class="p">{share}% margin{" so far" if j.status != "complete" else ""}</span>'
                      if share is not None else "")
        dot = "loss" if j.contribution is not None and j.contribution < 0 else j.status
        lines = [f'<tr><td>Sold for</td><td class="r">{_money(j.sales)}</td></tr>'] if j.invoice_lines else []
        lines += [f'<tr><td>{escape(CATEGORY_LABELS[c])}</td><td class="r">−{_money(j.costs[c])}</td></tr>'
                  for c in CATEGORIES if j.costs[c]]
        if j.contribution is not None:
            lines.append(f'<tr class="tot"><td>Left after job costs</td><td class="r">{amount}</td></tr>')
        why = f'<div class="why">{escape(" ".join(j.reasons))}</div>' if j.reasons else ""
        price = pricing(j, summary.usual_margin)
        tip = ""
        if price and (j.contribution < 0 or (price["at_usual"] is not None and price["at_usual"] > j.sales)):
            parts = []
            if j.contribution < 0:
                parts.append(f"Break-even price: {_money(price['break_even'])}")
            if price["at_usual"] is not None and price["at_usual"] > j.sales:
                parts.append(f"At your usual {price['usual']}% margin: about {_money(price['at_usual'])}")
            tip = f'<div class="price">{" · ".join(parts)}</div>'
        rows.append(f'<details class="mx-d"><summary><div class="mx-job"><span class="mx-dot {dot}"></span>'
                    f'<div class="w">{what}<span class="mx-chev">›</span> <small>· {who} · {escape(j.job_id)}</small></div>'
                    f'<div class="tagc"><span class="mx-tag {j.status}">{tag[j.status]}</span></div>'
                    f'<div class="a{neg}">{amount}{share_html}</div></div></summary>'
                    f'<div class="mx-break"><table>{"".join(lines)}</table>{why}{tip}</div></details>')
    _html(f'<div class="mx-card"><h3>Jobs <span style="font-weight:400;font-size:.85rem;color:#5A6F66">'
          f'· click a job to see why</span></h3>{"".join(rows)}</div>')
