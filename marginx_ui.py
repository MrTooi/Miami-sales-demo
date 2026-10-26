"""MargenX look and feel: brand styles and the HTML for the results screen.

Light, calm and plain-spoken, matching the website: mint background, white cards, dark-green
accents. No web fonts or other outside requests: the page works offline, as the pilot promises.

Streamlit reads Markdown in st.markdown, messages, captions, widget labels and radio choices, and
Markdown can load an image from the internet (![x](https://...)). So text from a file never reaches
Markdown as-is: HTML blocks are kept on one line (a blank line would end the HTML block and start
Markdown), and plain-text calls go through md_text(). Every value that can come from a shop's file (customer names, job descriptions,
reasons) is HTML-escaped here before it reaches the page.
"""
from __future__ import annotations

import base64
import re
from html import escape
from pathlib import Path

import streamlit as st

from job_profit import CATEGORIES, CATEGORY_LABELS, ProfitReport
from marginx_insights import Insight, Summary, money, percent, pricing

BRAND = "MargenX"  # the product name, in one place
# Fits every kind of business MargenX is for: those that quote, do and bill work by the job.
TAGLINE = "See which jobs make you money, and which lose it"

_CSS = """
<style>
/* No web fonts: the page makes no outside requests. Brand fonts are used only if installed. */
:root{--mx-green:#0F7A55;--mx-green-dark:#0B5C40;--mx-mint:#E6F6EE;--mx-mint-2:#F4FBF7;--mx-ink:#0E241B;
--mx-muted:#5A6F66;--mx-line:#DCEDE5;--mx-card:#FFFFFF;--mx-red:#B42318;--mx-red-bg:#FDECEA;--mx-amber:#9A5B05;
--mx-amber-bg:#FEF4E2;--mx-blue:#1E5C8C;--mx-blue-bg:#E8F1F9}
html,body,[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,var(--mx-mint) 0%,var(--mx-mint-2) 420px)!important;color:var(--mx-ink)}
[data-testid="stHeader"]{background:transparent!important}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"]{display:none!important}
[data-testid="stAppViewContainer"] *{font-family:'Inter',system-ui,sans-serif}
[data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded'!important}
.block-container{max-width:1080px;padding-top:2.2rem;padding-bottom:4rem}
h1,h2,h3,.mx-h{font-family:'Plus Jakarta Sans','Inter',system-ui,sans-serif!important;color:var(--mx-ink)!important;letter-spacing:-.02em}
.mx-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:6px}
.mx-brand{display:flex;align-items:center;gap:10px;font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:800;font-size:1.25rem;color:var(--mx-ink)}
.mx-brand b{color:var(--mx-green)}
.mx-logo{width:38px;height:42px;object-fit:contain;display:block}
.mx-pill{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:600;padding:5px 11px;border-radius:999px;background:var(--mx-amber-bg);color:var(--mx-amber)}
.mx-pill.pilot{background:var(--mx-blue-bg);color:var(--mx-blue)}
.mx-steps{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 22px}
.mx-step{font-size:.85rem;padding:7px 13px;border-radius:999px;background:rgba(255,255,255,.55);color:var(--mx-muted);border:1px solid var(--mx-line)}
.mx-step.on{background:var(--mx-green);color:#fff;border-color:var(--mx-green);font-weight:600}
.mx-step.done{color:var(--mx-green);font-weight:600}
.mx-kicker{color:var(--mx-muted);font-size:.9rem;margin:2px 0 4px}
.mx-title{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:800;font-size:2.05rem;line-height:1.12;letter-spacing:-.03em;margin:0 0 18px;color:var(--mx-ink)}
.mx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.mx-metric{background:var(--mx-card);border:1px solid var(--mx-line);border-radius:16px;padding:16px 18px;box-shadow:0 1px 2px rgba(14,36,27,.04)}
.mx-metric .l{font-size:.82rem;color:var(--mx-muted);font-weight:500}
.mx-metric .v{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:1.65rem;font-weight:800;letter-spacing:-.02em;margin-top:4px;color:var(--mx-ink)}
.mx-metric .s{font-size:.8rem;color:var(--mx-muted);margin-top:2px}
.mx-metric .v.red{color:var(--mx-red)}.mx-metric .v.amber{color:var(--mx-amber)}.mx-metric .v.green{color:var(--mx-green)}
.mx-card{background:var(--mx-card);border:1px solid var(--mx-line);border-radius:18px;padding:18px 22px;margin-bottom:16px;box-shadow:0 1px 2px rgba(14,36,27,.04)}
.mx-card h3{font-size:1.05rem!important;margin:0 0 10px!important;font-weight:700}
.mx-item{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-top:1px solid var(--mx-line)}
.mx-item:first-of-type{border-top:0}
.mx-ico{flex:0 0 30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.95rem}
.mx-ico.loss{background:var(--mx-red-bg);color:var(--mx-red)}.mx-ico.warn{background:var(--mx-amber-bg);color:var(--mx-amber)}.mx-ico.info{background:var(--mx-blue-bg);color:var(--mx-blue)}
.mx-item .t{font-weight:600;color:var(--mx-ink)}.mx-item .d{font-size:.88rem;color:var(--mx-muted);margin-top:2px}
.mx-row{display:grid;grid-template-columns:minmax(0,1.6fr) repeat(3,minmax(0,1fr));gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--mx-line)}
.mx-row>div:not(.n){text-align:right;font-variant-numeric:tabular-nums}.mx-row .lft{font-weight:700;font-family:'Plus Jakarta Sans',system-ui,sans-serif}
.mx-row.head{font-size:.8rem;color:var(--mx-muted);padding:2px 0 6px;border-top:0}.mx-row.loss .lft,.mx-row.loss .mg{color:var(--mx-red)}
.mx-row .n small.chk{display:inline-block;margin-top:3px;font-size:.75rem;padding:1px 8px;border-radius:999px;background:var(--mx-amber-bg);color:var(--mx-amber)}
.mx-row:first-of-type{border-top:0}
.mx-row .n{font-weight:600}.mx-row .n small{display:block;font-weight:400;color:var(--mx-muted);font-size:.8rem}
.mx-job{display:grid;grid-template-columns:12px minmax(0,1fr) auto 120px;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--mx-line);font-size:.95rem}
.mx-job:first-of-type{border-top:0}
.mx-dot{width:10px;height:10px;border-radius:50%}.mx-dot.complete{background:var(--mx-green)}.mx-dot.loss{background:var(--mx-red)}.mx-dot.provisional{background:#E0A43A}.mx-dot.unavailable{background:#B7C4BE}
.mx-job .w small{color:var(--mx-muted);font-size:.82rem}
.mx-tag{font-size:.75rem;padding:3px 9px;border-radius:999px;white-space:nowrap}
.mx-tag.complete{background:var(--mx-mint);color:var(--mx-green-dark)}.mx-tag.provisional{background:var(--mx-amber-bg);color:var(--mx-amber)}.mx-tag.unavailable{background:#EEF2F0;color:var(--mx-muted)}
.mx-job .a{text-align:right;font-weight:700;font-family:'Plus Jakarta Sans',system-ui,sans-serif}.mx-job .a.neg{color:var(--mx-red)}
.mx-after{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#fff;border:1px dashed #BFE3D2;border-radius:14px;padding:12px 18px;margin:-4px 0 18px;font-size:.9rem;color:var(--mx-muted)}
.mx-after b{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:1.15rem;color:var(--mx-ink)}
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
.mx-job .a .p{display:block;font-size:.75rem;font-weight:500;color:var(--mx-muted);font-family:'Inter',system-ui,sans-serif}
.mx-legend{font-size:.78rem;color:var(--mx-muted);margin-top:8px}
.mx-fine{margin:18px 4px 4px;line-height:1.45}
.mx-legend span{display:inline-block;width:12px;height:7px;border-radius:3px;margin:0 5px 1px 0;vertical-align:middle}
.mx-foot{font-size:.82rem;color:var(--mx-muted);margin:4px 2px 18px}
.mx-file{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:700;font-size:1rem;margin:14px 0 2px;color:var(--mx-ink)}
.mx-section{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:800;font-size:1.25rem;margin:26px 0 6px;color:var(--mx-ink)}
div.stButton>button{border-radius:11px!important;border:1px solid var(--mx-line)!important;background:#fff!important;color:var(--mx-ink)!important;font-weight:600!important}
div.stButton>button:hover{border-color:var(--mx-green)!important;color:var(--mx-green)!important}
div[data-testid="stExpander"]{border:1px solid var(--mx-line)!important;border-radius:14px!important;background:rgba(255,255,255,.7)!important}
[data-testid="stDataFrame"]{border:1px solid var(--mx-line);border-radius:12px;overflow:hidden}
.stAlert{border-radius:14px!important}
div[data-testid="stAlertContentWarning"]{font-size:.88rem}
@media(max-width:700px){.mx-title{font-size:1.6rem}.mx-metric{padding:12px 14px}.mx-metric .v{font-size:1.3rem}.mx-row{grid-template-columns:minmax(0,1.2fr) repeat(3,minmax(0,1fr));gap:8px;font-size:.88rem}
/* A phone has no room for the status column, so "Needs a check" moves under the job name: never hidden. */
.mx-job{grid-template-columns:12px minmax(0,1fr) 96px;row-gap:4px}.mx-job .tagc{grid-column:2;grid-row:2}}
</style>
"""

# The MargenX logo (assets/margenx-logo.png), embedded in the page as image data so the header
# never loads anything from outside: the app works offline and the static demo page stays self-contained.
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "margenx-logo.png"
_LOGO_SRC = "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def apply_brand() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# The app frame (top bar, steps column, consent and upload cards): the import page only, never the
# static demo page, which has no upload of any kind.
_APP_CSS = """
<style>
/* The app frame: a dark top bar, a steps column and the page beside it (the import page only). */
.block-container:has(.st-key-mx-bar){max-width:none;padding:0 0 3rem}
[data-testid="stHeader"]{display:none!important}
[data-testid="stElementContainer"]:has(>[data-testid="stMarkdown"] style){display:none}
.st-key-mx-bar{background:#0F1F19;padding:10px 28px;border-bottom:1px solid #1C3329}
/* On a laptop or tablet the bar stays at the top while the page scrolls, so End session is always one click
   away. Streamlit wraps the bar in a box of its own height, so that box is what sticks. Not on a phone: there
   the bar takes three lines and would cover a sixth of the screen. */
@media(min-width:701px){[data-testid="stLayoutWrapper"]:has(>.st-key-mx-bar){position:sticky;top:0;z-index:999}}
.st-key-mx-bar div.stButton>button{background:transparent!important;color:#E8EFEC!important;border:1px solid #3A5247!important}
.st-key-mx-bar div.stButton>button:hover{border-color:#1DBA85!important;color:#7FE0B9!important}
/* The End session label is never cut off: it wraps onto two lines on a narrow screen. */
.st-key-mx-bar div.stButton>button p{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.2;font-size:.85rem}
@media(max-width:1250px){.mx-bar .ws,.mx-bar .sep{display:none}}
/* On a phone the session pill drops under the logo instead of running off the screen. */
.mx-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;min-height:44px}
.mx-bar .mx-logo{width:34px;height:36px}
.mx-bar .name{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:800;font-size:1.2rem;color:#E8EFEC}.mx-bar .name b{color:#1DBA85}
.mx-bar .sep{width:1px;height:24px;background:#2A4237}
.mx-bar .ws{font-size:.9rem;color:#9FB2AB;font-weight:500}
.mx-live{margin-left:auto;display:inline-flex;align-items:center;gap:8px;font-size:.8rem;color:#7FE0B9;background:rgba(29,186,133,.12);border:1px solid rgba(29,186,133,.3);padding:5px 12px;border-radius:999px;white-space:nowrap}
.mx-live.demo{color:#F6C978;background:rgba(246,201,120,.1);border-color:rgba(246,201,120,.3)}
.mx-live i{width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px rgba(29,186,133,.18)}
.st-key-mx-ended{padding:16px 40px 0}
/* Dropdowns (the "which job" step): a long choice ends in "…" instead of a hard cut, and on a phone each choice in
   the open list gets two smaller lines. The list's rows are a fixed 40px, so two lines is the most that fits. */
[data-testid="stSelectbox"] input{text-overflow:ellipsis}
@media(max-width:700px){[data-testid="stSelectboxVirtualDropdown"] [role="option"]>div{white-space:normal;overflow:hidden;font-size:.75rem;line-height:1.15;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
.st-key-mx-shell>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{gap:0!important}
.st-key-mx-shell>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:first-child{background:#F7FBF9;border-right:1px solid #DCE9E2;padding:26px 18px;min-height:calc(100vh - 66px)}
.st-key-mx-shell>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:last-child{padding:26px 40px 0}
.mx-nav-l{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#7A8C84;font-weight:600;margin:0 10px 12px}
.mx-nav{display:flex;gap:12px;align-items:flex-start;padding:11px 10px;border-radius:12px;border:1px solid transparent}
.mx-nav.on{background:#fff;box-shadow:0 1px 3px rgba(14,36,27,.08);border-color:#DCE9E2}
.mx-nav .n{flex:0 0 28px;height:28px;border-radius:50%;border:1.5px solid #BFD3C9;color:#7A8C84;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:700}
.mx-nav.on .n{background:#1DBA85;border-color:#1DBA85;color:#0E241B}.mx-nav.done .n{border-color:#1DBA85;color:#0F7A55}
.mx-nav .t{font-size:.88rem;font-weight:600;color:#33493F}.mx-nav.on .t{color:#0E241B}.mx-nav .d{font-size:.76rem;color:#7A8C84;margin-top:2px}
.mx-nav .n svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
.mx-nav-line{width:1.5px;height:12px;background:#D3E2DA;margin:2px 0 2px 23px}
.mx-get{margin-top:22px;padding:16px;border-radius:14px;background:linear-gradient(160deg,#103026,#0F1F19);color:#D7E4DF}
.mx-get .h{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#7FE0B9;font-weight:600;margin-bottom:6px}
.mx-get .i{font-size:.82rem;padding:6px 0;display:flex;gap:8px;border-top:1px solid rgba(255,255,255,.07)}.mx-get .i:first-of-type{border-top:0}.mx-get .i span{color:#1DBA85}
.mx-stephead .c{font-size:.82rem;color:#7A8C84}.mx-stephead h1{font-size:1.75rem!important;margin:2px 0 4px!important;padding:0!important}
.mx-stephead p{font-size:.95rem;color:#5A6F66;margin:0 0 6px}
.st-key-mx-consent,.st-key-mx-files{background:#fff;border:1px solid #DCE9E2;border-radius:16px;padding:20px 22px;box-shadow:0 1px 2px rgba(14,36,27,.04)}
.mx-cardt{font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-weight:700;font-size:1rem;color:var(--mx-ink)}.mx-cards{font-size:.82rem;color:#7A8C84;margin-top:2px}
.st-key-mx-consent [data-testid="stCheckbox"]{background:#F4FAF7;border:1px solid #E1EEE7;border-radius:12px;padding:14px}
/* The consent is always shown in full, never cut to one line. */
.st-key-mx-consent [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"],.st-key-mx-consent [data-testid="stCheckbox"] p{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.55}
.mx-trust{display:flex;flex-direction:column;gap:10px;border-left:1px solid #E1EEE7;padding-left:22px}
.mx-trust div{display:flex;gap:10px;align-items:center;font-size:.84rem;color:#33493F}
.mx-ico2{flex:0 0 28px;width:28px;height:28px;border-radius:8px;background:#E6F6EE;color:#0F7A55;display:flex;align-items:center;justify-content:center}
.mx-ico2 svg,.mx-drop .big svg,.mx-lock svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.mx-drop,.st-key-mx-files [data-testid="stFileUploaderDropzone"]{border:2px dashed #A9D9C3!important;border-radius:14px!important;background:repeating-linear-gradient(135deg,#FAFDFB 0 14px,#F4FAF7 14px 28px)!important;min-height:230px}
.mx-drop{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;margin-top:4px}
.mx-drop .big{width:52px;height:52px;border-radius:15px;background:#0F1F19;color:#1DBA85;display:flex;align-items:center;justify-content:center;margin-bottom:12px;opacity:.8}
.mx-drop .big svg{width:24px;height:24px}
.mx-drop .t{font-weight:700;font-size:.95rem;color:#33493F}.mx-drop .d{font-size:.82rem;color:#5A6F66;margin-top:4px}
.mx-lock{display:inline-flex;gap:6px;align-items:center;font-size:.76rem;color:#9A6A12;background:#FEF4E2;border-radius:999px;padding:4px 10px;margin-top:12px}
.st-key-mx-files [data-testid="stFileUploaderDropzone"]{flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:12px}
.st-key-mx-files [data-testid="stFileUploaderDropzone"]::before{content:"Drop your sales and cost reports here";font-weight:700;font-size:.95rem;color:#33493F}
.st-key-mx-files [data-testid="stFileUploaderDropzoneInstructions"]{flex:0 0 auto!important;justify-content:center;font-size:.82rem;color:#5A6F66}
.st-key-mx-files [data-testid="stFileUploaderDropzone"] button{background:#0F1F19!important;color:#E8EFEC!important;border:0!important;border-radius:10px!important;padding:8px 18px!important}
.st-key-mx-files [data-testid="stFileUploaderDropzone"] button:hover{background:#1A3B2F!important;color:#7FE0B9!important}
.mx-slots{display:flex;gap:12px;margin-top:12px}.mx-slot{flex:1;border:1px solid #E1EEE7;border-radius:12px;padding:10px 12px;font-size:.84rem;color:#7A8C84;display:flex;gap:10px;align-items:center}
.mx-slot b{color:#0E241B;font-weight:600}.mx-slot.ok{border-color:#BFE3D2;background:#F4FBF7}.mx-slot.ok .mx-ico2{background:#1DBA85;color:#0E241B}
@media(max-width:900px){.st-key-mx-shell>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:first-child{min-height:0}.st-key-mx-shell>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:last-child{padding:20px 16px 0}.mx-trust{border-left:0;padding-left:0}.mx-slots{flex-direction:column}.mx-bar .ws{display:none}.st-key-mx-ended{padding:12px 16px 0}}
</style>
"""


def apply_app_frame() -> None:
    st.markdown(_APP_CSS, unsafe_allow_html=True)


_MD_LINK_CHARS = re.compile(r"([\\\[\]!<>])")


def md_text(value) -> str:
    """File text made safe for any Streamlit call that reads Markdown.

    Line breaks become spaces, and the characters that build images, links and HTML ([ ] ! < > and
    backslash) are backslash-escaped, so a cell like ![x](https://...) shows as text and never loads
    anything. Ordinary text, such as file names and sentences, looks the same.
    """
    return _MD_LINK_CHARS.sub(r"\\\1", re.sub(r"\s+", " ", str(value)).strip())


def _html(markup: str) -> None:
    # One line: a blank line inside a file value would end the HTML block and let Markdown run.
    st.markdown(re.sub(r"[\r\n]+", " ", markup), unsafe_allow_html=True)


def header(pilot: bool) -> None:
    pill = ('<span class="mx-pill pilot">Pilot session · this laptop only</span>' if pilot
            else '<span class="mx-pill">Example data only</span>')
    name = escape(BRAND)
    brand = f"<span>{name[:-1]}<b>{name[-1]}</b></span>" if name.endswith("X") else f"<span>{name}</span>"
    _html(f'<div class="mx-top"><div class="mx-brand"><img class="mx-logo" src="{_LOGO_SRC}" alt="{name} logo">'
          f'{brand}</div>{pill}</div>'
          f'<div class="mx-kicker">{escape(TAGLINE)}</div>')


# Small outline icons drawn inline (no icon font or image is loaded from anywhere).
_ICONS = {
    "laptop": '<path d="M4 6h16v10H4z"/><path d="M2 19h20"/>',
    "trash": '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
    "hand": '<path d="M8 13V5a1.5 1.5 0 0 1 3 0v6"/><path d="M11 11V4a1.5 1.5 0 0 1 3 0v7"/>'
            '<path d="M14 11V6a1.5 1.5 0 0 1 3 0v8a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-2-4a1.5 1.5 0 0 1 2.6-1.5L8 13"/>',
    "upload": '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "file": '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
}


def _icon(name: str) -> str:
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{_ICONS[name]}</svg>'


def top_bar(pilot: bool) -> None:
    """The app's top bar: logo, name, and whether this is a pilot session or made-up data only."""
    name = escape(BRAND)
    brand = f"{name[:-1]}<b>{name[-1]}</b>" if name.endswith("X") else name
    live = ('<span class="mx-live"><i></i>Pilot session · this laptop only</span>' if pilot
            else '<span class="mx-live demo"><i></i>Example data only</span>')
    _html(f'<div class="mx-bar"><img class="mx-logo" src="{_LOGO_SRC}" alt="{name} logo"><span class="name">{brand}</span>'
          f'<span class="sep"></span><span class="ws">{escape(TAGLINE)}</span>{live}</div>')


STEPS = (("Add your reports", "Sales and costs"), ("Answer a few questions", "Only if something's unclear"),
         ("See your money", "Profit by job and customer"))


def steps(current: int) -> None:
    """The check-up's three steps, down the side, with the current one highlighted."""
    rows = []
    for n, (title, note) in enumerate(STEPS, start=1):
        state = "on" if n == current else ("done" if n < current else "")
        mark = _icon("check") if n < current else str(n)
        rows.append(f'<div class="mx-nav {state}"><div class="n">{mark}</div><div><div class="t">{escape(title)}</div>'
                    f'<div class="d">{escape(note)}</div></div></div>')
    _html('<div class="mx-nav-l">Check-up</div>' + '<div class="mx-nav-line"></div>'.join(rows))


def what_you_get() -> None:
    # What the results show, without promising more: a figure is withheld or marked "Needs a check"
    # when costs are missing, and the margin is after job costs, before overhead.
    items = ("Profit by job and customer", "Jobs that lost money, and why", "Your margin after job costs",
             "Missing costs flagged, never guessed")
    _html('<div class="mx-get"><div class="h">You\'ll get</div>'
          + "".join(f'<div class="i"><span>✓</span>{escape(i)}</div>' for i in items) + "</div>")


def step_heading(step: int, title: str, lead: str) -> None:
    _html(f'<div class="mx-stephead"><div class="c">Step {step} of 3</div><h1>{escape(title)}</h1>'
          f'<p>{escape(lead)}</p></div>')


def card_title(title: str, note: str) -> None:
    _html(f'<div class="mx-cardt">{escape(title)}</div><div class="mx-cards">{escape(note)}</div>')


def privacy_points(pilot: bool) -> None:
    """What happens to the files, in three short lines (the consent box says it in full).

    "Stays on this laptop" is said only in a pilot session, which pilot_safety has verified runs on
    this laptop for a local browser. End session is an instruction, not a promise: when it can't
    confirm the files were cleared, the page says so.
    """
    first = (("laptop", "Stays on this laptop, never sent online") if pilot else ("file", "Made-up files only"))
    points = (first, ("lock", "Read in memory, never saved" if pilot else "Checked in memory, never saved"),
              ("trash", "End session clears the app's data"))
    _html('<div class="mx-trust">' + "".join(f'<div><span class="mx-ico2">{_icon(i)}</span>{escape(t)}</div>'
                                            for i, t in points) + "</div>")


def locked_drop() -> None:
    """Where the files go, shown locked until the box is ticked: no upload area exists before then."""
    _html(f'<div class="mx-drop"><div class="big">{_icon("upload")}</div>'
          '<div class="t">Drop your sales and cost reports here</div><div class="d">CSV or Excel</div>'
          f'<div class="mx-lock">{_icon("lock")}Tick the box above to choose files.</div></div>')


def file_slots(kinds: set[str]) -> None:
    """Whether a sales report and a cost report have been read (by what MargenX found, not file names)."""
    slots = []
    for kind, label in (("invoices", "Sales report"), ("costs", "Cost report")):
        ok = kind in kinds
        slots.append(f'<div class="mx-slot{" ok" if ok else ""}"><span class="mx-ico2">'
                     f'{_icon("check" if ok else "file")}</span><span><b>{label}</b> · {"read" if ok else "waiting"}'
                     "</span></div>")
    _html(f'<div class="mx-slots">{"".join(slots)}</div>')


def section(title: str) -> None:
    _html(f'<div class="mx-section">{escape(title)}</div>')


def file_title(name: str) -> None:
    _html(f'<div class="mx-file">{escape(name)}</div>')


def _money(amount) -> str:
    return escape(money(amount))


# Shown under every set of results, so nobody mistakes a rounded figure or an estimate for an exact
# fact, or the tool for professional advice.
READING_NOTE = ("How to read these numbers: sales and costs are added up exactly, to the cent, from the files you "
                "gave MargenX. Figures marked \"Needs a check\" may be missing costs. Percentages are rounded to "
                "whole numbers, and suggested prices are estimates. MargenX is a tool to help you look at your own "
                "numbers. It isn't accounting, tax or financial advice.")


def results(report: ProfitReport, summary: Summary, items: list[Insight], period: str) -> None:
    """The results screen: headline, key numbers, what needs attention, customers and jobs."""
    _html(f'<div class="mx-kicker">{escape(period)}</div><div class="mx-title">Here\'s where your money was made</div>')

    cards = []
    for label, value, sub, cls in _metrics(summary):
        cards.append(f'<div class="mx-metric"><div class="l">{escape(label)}</div><div class="v {cls}">{value}</div>'
                     f'<div class="s">{escape(sub)}</div></div>')
    _html(f'<div class="mx-grid">{"".join(cards)}</div>')
    after = _after_costs(summary)
    if after:
        main, note = after
        _html(f'<div class="mx-after"><div>{main}</div>'
              f'<div style="font-size:.8rem;max-width:320px;text-align:right">{escape(note)}</div></div>')

    if items:
        icons = {"loss": "↓", "warn": "!", "info": "i"}
        rows = "".join(f'<div class="mx-item"><div class="mx-ico {i.level}">{icons[i.level]}</div><div>'
                       f'<div class="t">{escape(i.title)}</div><div class="d">{escape(i.detail)}</div></div></div>'
                       for i in items)
        foot = ""
        if summary.usual_margin is not None and any("usual" in i.detail for i in items):
            foot = (f'<div class="mx-legend">Your usual margin ({percent(summary.usual_margin, 1)}%) is the share of sales '
                    "you kept across all your jobs with complete costs, added together.</div>")
        _html(f'<div class="mx-card"><h3>What needs your attention</h3>{rows}{foot}</div>')
    else:
        _html('<div class="mx-card"><h3>What needs your attention</h3><div class="mx-item"><div class="mx-ico info">✓</div>'
              '<div><div class="t">Nothing stands out</div><div class="d">No job lost money and every figure is complete.'
              '</div></div></div></div>')

    _customers(report)
    _jobs(report, summary)
    _html(f'<div class="mx-legend mx-fine">{READING_NOTE}</div>')



def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _left_out(summary: Summary) -> list[str]:
    """What the totals leave out, in words ("4 jobs without a figure", "2 rows that couldn't be read")."""
    parts = []
    if summary.jobs_without_figure:
        parts.append(f"{_plural(summary.jobs_without_figure, 'job')} without a figure")
    if summary.unlinked_sales_lines:
        parts.append(f"{money(summary.unlinked_sales)} of sales with no job number")
    unread = summary.rejected_sales_lines + summary.rejected_cost_lines
    if unread:
        parts.append(f"{_plural(unread, 'row')} that couldn't be read")
    return parts


def _unread_note(summary: Summary) -> str:
    """Says which file's rows couldn't be read, so a total is never taken for the whole file."""
    parts = []
    if summary.rejected_sales_lines:
        parts.append(f"{_plural(summary.rejected_sales_lines, 'sales row')}")
    if summary.rejected_cost_lines:
        parts.append(f"{_plural(summary.rejected_cost_lines, 'cost row')}")
    one = summary.rejected_sales_lines + summary.rejected_cost_lines == 1
    return f"{' and '.join(parts)} couldn't be read and {'isn' if one else 'aren'}'t included" if parts else ""


def _metrics(summary: Summary) -> list[tuple[str, str, str, str]]:
    """The four headline cards as (label, value HTML, plain-text note, colour class).

    "Left after job costs" always says which jobs it covers, so a partial total never reads as the whole.
    """
    sales_note = _plural(summary.jobs, "job")
    if summary.unlinked_sales_lines:
        sales_note += f" · {money(summary.unlinked_sales)} with no job number"
    if summary.rejected_sales_lines:
        sales_note += (f" · {_plural(summary.rejected_sales_lines, 'row')} couldn't be read and "
                       f"{'isn' if summary.rejected_sales_lines == 1 else 'aren'}'t included")
    if summary.jobs_with_figure:
        cover = (f"From {summary.jobs_with_figure} of {summary.jobs} jobs" if summary.figure_is_partial
                 else f"From all {_plural(summary.jobs, 'job')}")
        left_note = [cover]
        if summary.figure_is_provisional:
            left_note.append("some still need a check")
        if summary.rejected_sales_lines or summary.rejected_cost_lines:
            left_note.append(_unread_note(summary))
        left = (_money(summary.left_after_job_costs), " · ".join(left_note))
    else:
        left = ("—", "No job has a figure yet")
    # Only complete jobs count as confirmed losses; a loss so far on a job that needs a check is "may have".
    if summary.complete_jobs:
        losing = f"{summary.losing_jobs} of {summary.complete_jobs}"
        losing_note = [] if summary.complete_jobs == summary.jobs else ["jobs with complete costs"]
    else:
        losing, losing_note = "—", ["No job has complete costs yet"]
    if summary.possible_losses:
        more = " more" if summary.complete_jobs else ""
        needs = "needs" if summary.possible_losses == 1 else "need"
        losing_note.append(f"{summary.possible_losses}{more} may have lost money, still {needs} a check")
    return [
        ("Sales", _money(summary.sales), sales_note, ""),
        ("Left after job costs", left[0], left[1], ""),
        _margin_card(summary),
        ("Jobs losing money", losing, " · ".join(losing_note),
         "red" if summary.losing_jobs else ("amber" if summary.possible_losses else "green")),
    ]


def _margin_card(summary: Summary) -> tuple[str, str, str, str]:
    """Profit margin: the share of sales left after job costs, for the same jobs as "Left after job costs".

    A margin that includes jobs still needing a check may change either way (a missing cost makes it too
    high, a missing sale too low), so it says so and, when there are enough complete jobs, gives their
    margin too: the same "usual margin" the attention list uses.
    """
    if not summary.jobs_with_figure:
        return ("Profit margin", "—", "No job has a figure yet", "")
    if summary.share_percent is None:
        # Jobs have figures, but their sales add up to $0 or less (credits and refunds): a margin is a
        # share of sales, so there is none to show.
        return ("Profit margin", "—", f"Sales on these jobs add up to {money(summary.sales_with_figure)}, so there's "
                "no margin to show", "")
    note = ["After job costs, before rent and overhead"]
    if summary.figure_is_partial:
        note.append(f"from {summary.jobs_with_figure} of {summary.jobs} jobs")
    if summary.figure_is_provisional:
        note.append("may change, some jobs need a check")
        if summary.usual_margin is not None:
            note.append(f"jobs with complete costs: {percent(summary.usual_margin, 1)}%")
    return ("Profit margin", f"{summary.share_percent}%", " · ".join(note),
            "red" if summary.share_percent < 0 else "")


def _after_costs(summary: Summary) -> tuple[str, str] | None:
    """The line under the cards about costs not tied to any job, as (main HTML, plain-text note).

    It keeps overhead (rent, fees) apart from costs that simply have no job number, and gives a
    total only when every sale is in the job total; otherwise it says why the total is withheld.
    """
    if not summary.unlinked_costs:
        return None
    if summary.overhead_costs and summary.unassigned_job_costs:
        of_which = (f" ({money(summary.overhead_costs)} of overhead such as rent, and "
                    f"{money(summary.unassigned_job_costs)} with no job number that may belong to jobs)")
    elif summary.overhead_costs:
        of_which = " (overhead such as rent)"
    else:
        of_which = " (they have no job number and may belong to jobs)"
    costs = f"{_money(summary.unlinked_costs)} of costs not tied to any job{escape(of_which)}"
    if summary.after_unlinked_costs is None:
        parts = _left_out(summary)
        missing = (", ".join(parts[:-1]) + " and " + parts[-1]) if len(parts) > 1 else (parts[0] if parts
                                                                                         else "some sales")
        return (f"There are {costs}. A total after them isn't shown yet",
                f"The totals leave out {missing}, so a total after these costs could be wrong.")
    note = ("Sales minus every cost in these files, before tax. If any costs are missing from the files, "
            "your real profit is lower.")
    if summary.figure_is_provisional:
        note += " Some jobs still need a check, so this may be too high."
    # Shown only when every sale is in the job total, so its margin is of all sales.
    margin = percent(summary.after_unlinked_costs, summary.sales)
    margin_text = "" if margin is None else f", a {margin}% margin on all sales"
    return (f"After the {costs}, these files leave <b>{_money(summary.after_unlinked_costs)}</b>{margin_text}",
            note)


def _customers(report: ProfitReport) -> None:
    """A table of customers by what they leave you: sales, left after job costs and margin, nothing else."""
    counted = [c for c in report.customers if c.contribution is not None]
    if not counted:
        return
    rows = ['<div class="mx-row head"><div class="n">Customer</div><div>Sales</div><div>Left after job costs</div>'
            '<div>Margin</div></div>']
    for c in sorted(counted, key=lambda c: (-c.contribution, c.customer)):
        share = percent(c.contribution, c.sales)  # the same rounding as the attention list
        checked = c.status == "complete"
        # A customer whose jobs need a check may be missing costs: its margin is "so far", as in the job list.
        margin = "—" if share is None else f"{share}%{'' if checked else ' so far'}"
        note = "" if checked else '<small class="chk">Needs a check</small>'
        jobs = [j for j in report.jobs if j.job_id in c.jobs]
        inner = "".join(f'<tr><td>{escape(j.description or "Job")} · {escape(j.job_id)}</td>'
                        f'<td class="r">{"—" if j.contribution is None else _money(j.contribution)}</td></tr>'
                        for j in jobs)
        why = f'<div class="why">{escape(" ".join(c.reasons))}</div>' if c.reasons else ""
        rows.append(
            f'<details class="mx-d"><summary><div class="mx-row{" loss" if c.contribution < 0 else ""}">'
            f'<div class="n">{escape(c.customer)}<span class="mx-chev">›</span>{note}</div>'
            f'<div>{_money(c.sales)}</div><div class="lft">{_money(c.contribution)}</div>'
            f'<div class="mg">{margin}</div></div></summary>'
            f'<div class="mx-break"><table>{inner}</table>{why}</div></details>')
    legend = ""
    left_out = [c.customer for c in report.customers if c.contribution is None]
    if left_out:
        # The list must never read as every customer when some have no figure yet.
        legend = (f'<div class="mx-legend">Not listed, no figure yet: {escape(", ".join(left_out))}. '
                  "See the job list below.</div>")
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
        # A cost is subtracted; a net credit (a refund from a supplier) is added back, never shown as "−-$20".
        lines += [f'<tr><td>{escape(CATEGORY_LABELS[c])}{"" if j.costs[c] > 0 else " (credit)"}</td>'
                  f'<td class="r">{"−" if j.costs[c] > 0 else "+"}{_money(abs(j.costs[c]))}</td></tr>'
                  for c in CATEGORIES if j.costs[c]]
        if j.contribution is not None:
            lines.append(f'<tr class="tot"><td>Left after job costs</td><td class="r">{amount}</td></tr>')
        why = f'<div class="why">{escape(" ".join(j.reasons))}</div>' if j.reasons else ""
        price = pricing(j, summary.usual_margin)
        tip = ""
        if price and (j.contribution < 0 or (price["at_usual"] is not None and price["at_usual"] > j.sales)):
            parts = []
            if j.contribution < 0:
                parts.append(f"Price to cover its job costs (before overhead not assigned to this job): {_money(price['break_even'])}")
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
