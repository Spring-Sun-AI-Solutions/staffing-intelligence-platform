"""
app/theme.py
Shared UI layer — design tokens, CSS, reusable components, chart styling.

Import once per page:

    from app.theme import apply_theme, page_header, metric_row, badge

    apply_theme()
    page_header("Job Match", "Rank candidates against an open requisition")

Design principles
-----------------
1. Data is the hero. Chrome stays quiet.
2. Teal is brand and primary action only — never decoration.
3. Status colour is semantic. Red always means risk.
4. Tabular figures so numbers align in columns.
"""
import streamlit as st

# ── Design tokens ─────────────────────────────────────────────────────────────

INK        = "#111827"   # primary text
INK_MUTED  = "#6B7280"   # secondary text
INK_FAINT  = "#9CA3AF"   # tertiary / captions
RULE       = "#E5E7EB"   # borders
RULE_SOFT  = "#F0F1F3"   # inner dividers
SURFACE    = "#FFFFFF"
CANVAS     = "#F6F7F9"

BRAND      = "#0F766E"   # teal — primary actions and identity ONLY
BRAND_DEEP = "#115E59"
BRAND_WASH = "#ECFDF9"

# Semantic status — these mean something, never used decoratively
RISK       = "#B91C1C"
RISK_WASH  = "#FEF2F2"
WARN       = "#B45309"
WARN_WASH  = "#FFFBEB"
GOOD       = "#15803D"
GOOD_WASH  = "#F0FDF4"
INFO       = "#1D4ED8"
INFO_WASH  = "#EFF6FF"

# Ordered categorical palette for charts — distinct from status colours
SERIES = ["#0F766E", "#1D4ED8", "#B45309", "#7C3AED", "#0E7490", "#BE185D"]


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"], .stApp {{
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    font-feature-settings: 'tnum' 1, 'cv05' 1;
}}

/* Tighten the default Streamlit shell — reclaim vertical space */
.block-container {{
    padding-top: 2.2rem;
    padding-bottom: 3rem;
    max-width: 1400px;
}}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer {{ visibility: hidden; }}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid {RULE};
}}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1.5rem; }}

/* ── Page header ──────────────────────────────────────────────────────── */
.pg-head {{
    display: flex; align-items: baseline; gap: .75rem;
    padding-bottom: .55rem; margin-bottom: 1.4rem;
    border-bottom: 1px solid {RULE};
}}
.pg-title {{
    font-size: 1.35rem; font-weight: 600; color: {INK};
    letter-spacing: -0.015em; margin: 0; line-height: 1.2;
}}
.pg-sub {{
    font-size: .875rem; color: {INK_MUTED}; margin: 0;
}}
.pg-right {{ margin-left: auto; font-size: .8rem; color: {INK_FAINT}; }}

/* ── Metric cards ─────────────────────────────────────────────────────── */
.mrow {{ display: flex; gap: 0; border: 1px solid {RULE}; border-radius: 8px;
         overflow: hidden; margin-bottom: 1.5rem; background: {SURFACE}; }}
.mcell {{ flex: 1; padding: .85rem 1.1rem; border-right: 1px solid {RULE_SOFT}; }}
.mcell:last-child {{ border-right: none; }}
.mlabel {{ font-size: .75rem; color: {INK_MUTED}; margin-bottom: .3rem;
           font-weight: 500; }}
.mvalue {{ font-size: 1.6rem; font-weight: 600; color: {INK};
           line-height: 1.1; letter-spacing: -0.02em; }}
.mdelta {{ font-size: .75rem; margin-top: .25rem; font-weight: 500; }}
.mnote  {{ font-size: .75rem; color: {INK_FAINT}; margin-top: .25rem; }}

/* ── Badges — semantic only ───────────────────────────────────────────── */
.bdg {{
    display: inline-block; padding: .15rem .5rem; border-radius: 4px;
    font-size: .75rem; font-weight: 500; line-height: 1.5;
    white-space: nowrap;
}}
.bdg-risk {{ background: {RISK_WASH}; color: {RISK}; }}
.bdg-warn {{ background: {WARN_WASH}; color: {WARN}; }}
.bdg-good {{ background: {GOOD_WASH}; color: {GOOD}; }}
.bdg-info {{ background: {INFO_WASH}; color: {INFO}; }}
.bdg-mute {{ background: {CANVAS};    color: {INK_MUTED}; }}

/* ── Skill chips ──────────────────────────────────────────────────────── */
.chip {{
    display: inline-block; padding: .12rem .45rem; margin: 0 .25rem .3rem 0;
    border-radius: 4px; font-size: .75rem; font-family: 'IBM Plex Mono', monospace;
    background: {CANVAS}; color: {INK_MUTED}; border: 1px solid {RULE};
}}
.chip-have {{ background: {GOOD_WASH}; color: {GOOD}; border-color: #BBF7D0; }}
.chip-miss {{ background: {RISK_WASH}; color: {RISK}; border-color: #FECACA; }}

/* ── Score bar ────────────────────────────────────────────────────────── */
.sbar-wrap {{ display: flex; align-items: center; gap: .5rem; }}
.sbar {{ flex: 1; height: 5px; background: {RULE_SOFT}; border-radius: 3px;
         overflow: hidden; min-width: 60px; }}
.sbar-fill {{ height: 100%; border-radius: 3px; }}
.sbar-num {{ font-family: 'IBM Plex Mono', monospace; font-size: .8rem;
             font-weight: 500; color: {INK}; min-width: 34px; text-align: right; }}

/* ── Section label ────────────────────────────────────────────────────── */
.sect {{
    font-size: .8rem; font-weight: 600; color: {INK};
    margin: 1.6rem 0 .6rem 0; padding-bottom: .35rem;
    border-bottom: 1px solid {RULE_SOFT};
}}

/* ── Detail rows ──────────────────────────────────────────────────────── */
.drow {{ display: flex; justify-content: space-between; padding: .4rem 0;
         border-bottom: 1px solid {RULE_SOFT}; font-size: .85rem; }}
.drow:last-child {{ border-bottom: none; }}
.dkey {{ color: {INK_MUTED}; }}
.dval {{ color: {INK}; font-weight: 500; }}

/* ── Empty state ──────────────────────────────────────────────────────── */
.empty {{
    padding: 2.5rem 1.5rem; text-align: center; border: 1px dashed {RULE};
    border-radius: 8px; color: {INK_MUTED}; font-size: .875rem;
    background: {SURFACE};
}}

/* ── Streamlit widget refinements ─────────────────────────────────────── */
.stButton > button {{
    border-radius: 6px; font-weight: 500; font-size: .875rem;
    border: 1px solid {RULE}; transition: none;
}}
.stButton > button[kind="primary"] {{
    background: {BRAND}; border-color: {BRAND};
}}
.stButton > button[kind="primary"]:hover {{
    background: {BRAND_DEEP}; border-color: {BRAND_DEEP};
}}

div[data-testid="stDataFrame"] {{ border: 1px solid {RULE}; border-radius: 8px; }}

div[data-testid="stExpander"] {{
    border: 1px solid {RULE}; border-radius: 8px; background: {SURFACE};
}}
div[data-testid="stExpander"] summary {{ font-size: .875rem; font-weight: 500; }}

/* Tabs — flatten Streamlit's default pill look */
button[data-baseweb="tab"] {{
    font-size: .875rem; font-weight: 500; padding: .5rem .9rem;
}}
div[data-baseweb="tab-highlight"] {{ background-color: {BRAND}; }}

/* Inputs */
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
    border-radius: 6px; font-size: .875rem;
}}

/* Chat */
div[data-testid="stChatMessage"] {{
    background: {SURFACE}; border: 1px solid {RULE};
    border-radius: 8px; padding: .85rem 1rem;
}}
</style>
"""


def apply_theme():
    """Inject CSS. Call once at the top of every page, after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ── Components ────────────────────────────────────────────────────────────────

def page_header(title: str, subtitle: str = "", right: str = ""):
    """Consistent page header with a rule underneath."""
    sub   = f'<p class="pg-sub">{subtitle}</p>' if subtitle else ""
    rgt   = f'<div class="pg-right">{right}</div>' if right else ""
    st.markdown(
        f'<div class="pg-head"><h1 class="pg-title">{title}</h1>{sub}{rgt}</div>',
        unsafe_allow_html=True,
    )


def metric_row(metrics: list[dict]):
    """
    A single bordered row of KPIs — reads as one object rather than
    scattered cards.

        metric_row([
            {"label": "Candidates", "value": 80},
            {"label": "Placements", "value": 150, "delta": "+12", "good": True},
            {"label": "Avg margin", "value": "24.1%", "note": "target 25%"},
        ])
    """
    cells = []
    for m in metrics:
        parts = [
            f'<div class="mlabel">{m["label"]}</div>',
            f'<div class="mvalue">{m["value"]}</div>',
        ]
        if m.get("delta") is not None:
            col = GOOD if m.get("good", True) else RISK
            parts.append(f'<div class="mdelta" style="color:{col}">{m["delta"]}</div>')
        elif m.get("note"):
            parts.append(f'<div class="mnote">{m["note"]}</div>')
        cells.append(f'<div class="mcell">{"".join(parts)}</div>')
    st.markdown(f'<div class="mrow">{"".join(cells)}</div>', unsafe_allow_html=True)


def badge(label: str, level: str = "mute") -> str:
    """
    Semantic status badge. Returns HTML — use inside st.markdown.
    level: risk | warn | good | info | mute
    """
    return f'<span class="bdg bdg-{level}">{label}</span>'


def risk_badge(score: float, high: float = 0.6, med: float = 0.35) -> str:
    """Badge for a 0–1 risk score, coloured by threshold."""
    if score is None:
        return badge("—", "mute")
    if score >= high:
        return badge(f"High {score:.0%}", "risk")
    if score >= med:
        return badge(f"Medium {score:.0%}", "warn")
    return badge(f"Low {score:.0%}", "good")


def score_bar(value: float, maximum: float = 100) -> str:
    """Horizontal score bar with the number alongside. Returns HTML."""
    pct = max(0, min(100, value / maximum * 100))
    col = GOOD if pct >= 70 else WARN if pct >= 45 else RISK
    return (
        f'<div class="sbar-wrap">'
        f'<div class="sbar"><div class="sbar-fill" '
        f'style="width:{pct}%;background:{col}"></div></div>'
        f'<div class="sbar-num">{value:.0f}</div></div>'
    )


def skill_chips(skills: list, missing: list = None) -> str:
    """Skill chips. Anything in `missing` renders as a gap."""
    missing_lower = {s.lower() for s in (missing or [])}
    out = []
    for s in skills or []:
        cls = "chip chip-miss" if s.lower() in missing_lower else "chip chip-have"
        out.append(f'<span class="{cls}">{s}</span>')
    for s in missing or []:
        if s.lower() not in {x.lower() for x in (skills or [])}:
            out.append(f'<span class="chip chip-miss">{s}</span>')
    return "".join(out) or f'<span class="chip">none listed</span>'


def section(label: str):
    """Subsection label with a hairline rule."""
    st.markdown(f'<div class="sect">{label}</div>', unsafe_allow_html=True)


def detail_rows(pairs: list[tuple]):
    """Key/value list for detail panels."""
    rows = "".join(
        f'<div class="drow"><span class="dkey">{k}</span>'
        f'<span class="dval">{v}</span></div>'
        for k, v in pairs
    )
    st.markdown(rows, unsafe_allow_html=True)


def empty_state(message: str):
    """Empty state — an invitation to act, not an apology."""
    st.markdown(f'<div class="empty">{message}</div>', unsafe_allow_html=True)


# ── Chart styling ─────────────────────────────────────────────────────────────

def style_chart(fig, height: int = 320, showlegend: bool = False):
    """
    Apply consistent chart styling. Strips Plotly's default chrome so the
    data carries the visual weight.
    """
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        margin=dict(l=8, r=8, t=28, b=8),
        font=dict(family="IBM Plex Sans, sans-serif", size=12, color=INK),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=RULE,
            font=dict(family="IBM Plex Sans, sans-serif", size=12, color=INK),
        ),
        title=dict(font=dict(size=13, weight=600), x=0, xanchor="left"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=11)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=RULE,
                     tickfont=dict(size=11, color=INK_MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=RULE_SOFT, zeroline=False,
                     linecolor="rgba(0,0,0,0)",
                     tickfont=dict(size=11, color=INK_MUTED))
    return fig


def require_auth():
    """Guard for every page. Returns the current role."""
    if "username" not in st.session_state:
        st.warning("Sign in from the home page to continue.")
        st.stop()
    return st.session_state.get("role", "recruiter")
