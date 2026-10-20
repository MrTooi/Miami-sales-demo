"""Shared presentation system for the LEDGER Streamlit interface."""
import html
import streamlit as st

BUILD = "UI-2026.10.12"


def apply_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
        :root{--bg:#0B0F0D;--surface:#121714;--surface2:#171D1A;--border:#29322D;--text:#F3F6F1;--muted:#97A39B;--accent:#C8F36B}
        html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important}
        [data-testid="stHeader"]{background:rgba(11,15,13,.96)!important;border-bottom:1px solid rgba(41,50,45,.75)}
        [data-testid="stAppViewContainer"] *{font-family:'DM Sans',sans-serif}
        [data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded'!important}
        .block-container{max-width:1180px;padding-top:5.2rem;padding-bottom:4rem}
        h1,h2,h3{font-family:'Manrope',sans-serif!important;color:var(--text)!important;letter-spacing:-.035em!important}
        .ledger-topbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:28px}
        .ledger-brand-wrap{display:flex;align-items:center;gap:12px;min-width:0}
        .ledger-mark{width:38px;height:38px;border-radius:11px;background:var(--accent);color:#10150F;display:flex;align-items:center;justify-content:center;font-family:'Manrope',sans-serif;font-weight:800;font-size:1.08rem;letter-spacing:-.04em;flex:0 0 auto}
        .ledger-brand{font-family:'Manrope',sans-serif;font-size:1rem;font-weight:800;letter-spacing:.10em;line-height:1.1}
        .ledger-brand-sub{color:var(--muted);font-size:.78rem;margin-top:3px}
        .env-pill,.status-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--border);border-radius:999px;padding:7px 11px;color:#C5CEC8;background:var(--surface);font-size:.74rem;font-weight:700;letter-spacing:.04em;white-space:nowrap}
        .status-pill.good{color:#DDF9A4;border-color:#415432;background:#152012}.status-pill.warn{color:#F3D994;border-color:#594B2D;background:#1F1A10}.status-pill.dim{color:#BCC6BF}
        .status-dot{width:7px;height:7px;border-radius:999px;background:currentColor;opacity:.85}
        .hero{margin:2px 0 24px}.hero-kicker{color:var(--accent);font-size:.72rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase;margin-bottom:8px}
        .hero-title{font-family:'Manrope',sans-serif;font-size:2.25rem;font-weight:750;letter-spacing:-.045em;line-height:1.05;margin:0}.hero-sub{color:var(--muted);font-size:.98rem;max-width:720px;line-height:1.55;margin-top:10px}
        .demo-note{border:1px solid #3A452A;background:#151A10;color:#C8D2BF;border-radius:12px;padding:10px 13px;font-size:.82rem;margin:0 0 18px}
        .section-title{font-family:'Manrope',sans-serif;font-size:1.22rem;font-weight:750;letter-spacing:-.025em;margin-bottom:3px;color:var(--text)}.section-sub{color:var(--muted);font-size:.82rem;margin-bottom:14px}
        .confidence-card{border:1px solid var(--border);border-radius:14px;background:var(--surface);padding:14px 16px;margin:12px 0 18px}.confidence-label{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;font-weight:700}.confidence-value{font-family:'Manrope',sans-serif;font-weight:700;margin-top:5px}
        [data-testid="stMetric"]{background:linear-gradient(180deg,var(--surface2),var(--surface));border:1px solid var(--border);border-radius:15px;padding:18px 18px 16px;box-shadow:0 10px 28px rgba(0,0,0,.10);min-height:112px}
        [data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:.74rem!important;font-weight:700!important;letter-spacing:.05em;text-transform:uppercase}
        [data-testid="stMetricValue"]{color:var(--text)!important;font-family:'Manrope',sans-serif!important;font-size:1.55rem!important;letter-spacing:-.035em}
        div[data-testid="stExpander"]{border:1px solid var(--border)!important;background:var(--surface)!important;border-radius:14px!important;overflow:hidden}div[data-testid="stExpander"] details summary p{color:#E8EDE9!important;font-weight:600!important;white-space:normal!important}
        [data-testid="stTabs"] [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid var(--border);margin-bottom:12px;overflow-x:auto}[data-testid="stTabs"] [data-baseweb="tab"]{color:#AEB8B1!important;padding:10px 14px!important;font-size:.88rem!important;white-space:nowrap}[data-testid="stTabs"] [aria-selected="true"]{color:var(--text)!important}[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:var(--accent)!important}
        div.stButton>button,div.stDownloadButton>button{border-radius:11px!important;min-height:42px;font-weight:700!important;transition:transform .12s ease}div.stDownloadButton>button{background:var(--accent)!important;color:#131912!important;border:1px solid var(--accent)!important}div.stButton>button:hover,div.stDownloadButton>button:hover{transform:translateY(-1px)}
        [data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:12px;overflow:hidden}.stAlert{border-radius:12px!important;border-width:1px!important}hr{border-color:var(--border)!important;margin:1.5rem 0!important}
        .footerline{margin-top:28px;padding-top:18px;border-top:1px solid var(--border);display:flex;justify-content:space-between;gap:12px;color:#748078;font-size:.72rem;letter-spacing:.03em}
        @media(max-width:760px){.block-container{padding:5.6rem .9rem 3rem}.ledger-topbar{align-items:flex-start;margin-bottom:20px}.ledger-brand-sub{display:none}.env-pill{font-size:.68rem;padding:6px 9px}.hero-title{font-size:1.72rem}.hero-sub{font-size:.9rem}[data-testid="stMetric"]{padding:14px;min-height:96px}[data-testid="stMetricValue"]{font-size:1.22rem!important}[data-testid="stMetricLabel"]{font-size:.66rem!important}[data-testid="stHorizontalBlock"]{gap:.65rem!important}.footerline{flex-direction:column}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    st.markdown(
        """
        <div class="ledger-topbar">
          <div class="ledger-brand-wrap"><div class="ledger-mark">L</div><div><div class="ledger-brand">LEDGER</div><div class="ledger-brand-sub">Financial intelligence for operators</div></div></div>
          <div class="env-pill">DEVELOPMENT DEMO</div>
        </div>
        <div class="hero"><div class="hero-kicker">Business overview</div><div class="hero-title">Know what the business is actually earning.</div><div class="hero-sub">Revenue, costs, profitability, and data quality in one operating view — with every number tied back to the records behind it.</div></div>
        <div class="demo-note"><strong>Demo environment.</strong> Use fictional or anonymized records only. This build is not yet approved for confidential financial data.</div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title, subtitle=None):
    subtitle_html = f'<div class="section-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="section-title">{html.escape(title)}</div>{subtitle_html}', unsafe_allow_html=True)


def confidence_card(label, detail, tone="dim", heading="Data confidence"):
    st.markdown(
        f'<div class="confidence-card"><div class="confidence-label">{html.escape(heading)}</div><div style="margin-top:8px"><span class="status-pill {tone}"><span class="status-dot"></span>{html.escape(label)}</span></div><div class="section-sub" style="margin:9px 0 0">{html.escape(detail)}</div></div>',
        unsafe_allow_html=True,
    )


def render_footer():
    st.markdown(
        f'<div class="footerline"><span>LEDGER · Development build</span><span>{BUILD} · Not for confidential client information</span></div>',
        unsafe_allow_html=True,
    )
