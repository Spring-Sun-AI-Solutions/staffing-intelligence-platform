"""
app.py
Staffing Intelligence Platform — entry point.

Handles auth, navigation, and the landing overview.
Run: streamlit run app.py
"""
from dotenv import load_dotenv
load_dotenv()                      # must precede any project import

import streamlit as st
import yaml
import streamlit_authenticator as stauth
from pathlib import Path

st.set_page_config(
    page_title="Staffing Intelligence",
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.theme import (
    apply_theme, page_header, metric_row, badge, section,
    empty_state, style_chart, BRAND, INK_MUTED, RULE,
)
from data.logger import setup_root_logging

setup_root_logging(level="INFO")
apply_theme()

# ── Auth ──────────────────────────────────────────────────────────────────────
config_path = Path(__file__).parent / "auth_config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

authenticator.login(location="main")
auth_status = st.session_state.get("authentication_status")
name        = st.session_state.get("name")
username    = st.session_state.get("username")

if auth_status is False:
    st.error("Those credentials didn't match. Check the username and try again.")
    st.stop()
if auth_status is None:
    st.stop()

role = config["credentials"]["usernames"][username].get("role", "recruiter")
st.session_state["role"]     = role
st.session_state["username"] = username
st.session_state["name"]     = name

# ── Warm models + scheduler once per session ──────────────────────────────────
if "warmed" not in st.session_state:
    try:
        from ml.performance import warm_up_models
        from data.scheduler import start_scheduler
        warm_up_models()
        start_scheduler()
    except Exception:
        pass
    st.session_state["warmed"] = True

# ── Navigation ────────────────────────────────────────────────────────────────
ROLE_LABEL = {
    "recruiter":  "Recruiter",
    "manager":    "Manager",
    "exec":       "Executive",
    "compliance": "Compliance",
}

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:.55rem;'
        f'padding-bottom:.9rem;margin-bottom:.9rem;border-bottom:1px solid {RULE}">'
        f'<div style="width:26px;height:26px;border-radius:6px;background:{BRAND};'
        f'display:flex;align-items:center;justify-content:center;color:#fff;'
        f'font-weight:600;font-size:.8rem">◧</div>'
        f'<div style="font-weight:600;font-size:.9rem;line-height:1.1">'
        f'Staffing Intelligence</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="font-size:.85rem;font-weight:500">{name}</div>'
        f'<div style="font-size:.75rem;color:{INK_MUTED};margin-bottom:1rem">'
        f'{ROLE_LABEL.get(role, role)}</div>',
        unsafe_allow_html=True,
    )

    def nav_group(label: str, links: list[tuple]):
        st.markdown(
            f'<div style="font-size:.7rem;font-weight:600;color:{INK_MUTED};'
            f'margin:.9rem 0 .35rem 0">{label}</div>',
            unsafe_allow_html=True,
        )
        for path, text in links:
            st.page_link(path, label=text)

    nav_group("Talent", [
        ("pages/1_job_match.py",            "Job match"),
        ("pages/2_resume_parser.py",        "Resume parser"),
        ("pages/3_attrition_risk.py",       "Attrition risk"),
        ("pages/4_activity_recommender.py", "Today's queue"),
    ])

    nav_group("Assistant", [
        ("pages/5_ai_assistant.py", "Ask the assistant"),
        ("pages/15_jd_tools.py",    "Job descriptions"),
    ])

    if role in ("manager", "exec"):
        nav_group("Accounts", [
            ("pages/6_revenue_forecast.py",      "Revenue forecast"),
            ("pages/7_client_churn.py",          "Client churn"),
            ("pages/8_rate_optimizer.py",        "Rate guidance"),
            ("pages/9_recruiter_performance.py", "Recruiter KPIs"),
        ])

    if role == "exec":
        nav_group("Executive", [
            ("pages/12_placement_funnel.py",  "Placement funnel"),
            ("pages/13_margin_leakage.py",    "Margin leakage"),
            ("pages/14_executive_summary.py", "Summary"),
        ])

    if role == "compliance":
        nav_group("Compliance", [
            ("pages/10_visa_compliance.py",    "Visa tracking"),
            ("pages/11_timesheet_anomalies.py","Timesheet flags"),
        ])

    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    authenticator.logout(location="sidebar")

# ── Landing overview ──────────────────────────────────────────────────────────
first_name = (name or "there").split()[0]
page_header(
    f"Good to see you, {first_name}",
    "Here's where things stand across the desk today.",
)

try:
    from db.queries import get_candidates, get_clients, get_placements, get_open_jobs

    candidates = get_candidates()
    clients    = get_clients()
    placements = get_placements()
    open_jobs  = get_open_jobs()

    active = int(candidates["is_active_contractor"].sum()) if not candidates.empty else 0
    hires  = len(placements[placements["stage"] == "hire"]) if not placements.empty else 0
    subs   = len(placements)
    conv   = f"{hires / subs * 100:.0f}%" if subs else "—"

    metric_row([
        {"label": "Open requisitions", "value": len(open_jobs)},
        {"label": "Candidates",        "value": len(candidates),
         "note": f"{active} on assignment"},
        {"label": "Clients",           "value": len(clients)},
        {"label": "Submissions",       "value": subs},
        {"label": "Conversion",        "value": conv,
         "note": f"{hires} hires"},
    ])

    left, right = st.columns([3, 2], gap="large")

    with left:
        section("Needs attention")

        flagged = []

        if not candidates.empty and "attrition_risk_score" in candidates:
            at_risk = candidates[
                candidates["attrition_risk_score"].notna()
                & (candidates["attrition_risk_score"] > 0.6)
            ]
            if len(at_risk):
                flagged.append((
                    "risk",
                    f"{len(at_risk)} contractors at high attrition risk",
                    "Attrition risk",
                    "pages/3_attrition_risk.py",
                ))

        try:
            from db.queries import get_timesheets
            ts = get_timesheets(flagged_only=True)
            if len(ts):
                flagged.append((
                    "warn",
                    f"{len(ts)} timesheets flagged for review",
                    "Timesheet flags",
                    "pages/11_timesheet_anomalies.py",
                ))
        except Exception:
            pass

        if not clients.empty:
            thin = clients[clients["margin_pct"] < 12]
            if len(thin):
                flagged.append((
                    "warn",
                    f"{len(thin)} accounts running below 12% margin",
                    "Margin leakage",
                    "pages/13_margin_leakage.py",
                ))

        quiet = open_jobs.head(0)
        if not open_jobs.empty and not placements.empty:
            counts = placements.groupby("job_id").size()
            quiet = open_jobs[~open_jobs["id"].isin(counts.index)]
            if len(quiet):
                flagged.append((
                    "info",
                    f"{len(quiet)} open reqs with no submissions yet",
                    "Job match",
                    "pages/1_job_match.py",
                ))

        if flagged:
            for level, text, link_label, link in flagged:
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(
                        f'{badge(level.upper() if level != "info" else "OPEN", level)} '
                        f'<span style="font-size:.875rem">{text}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.page_link(link, label="Open")
        else:
            empty_state("Nothing needs attention. Everything is within thresholds.")

    with right:
        section("Pipeline")
        if not placements.empty:
            import plotly.graph_objects as go
            order = ["submitted", "interview", "offer", "hire"]
            counts = (placements[placements["stage"].isin(order)]
                      .groupby("stage").size().reindex(order).fillna(0))
            fig = go.Figure(go.Funnel(
                y=[s.title() for s in order],
                x=counts.tolist(),
                textinfo="value",
                marker_color=["#CBD5E1", "#94A3B8", "#0F766E", "#115E59"],
                connector=dict(line=dict(color=RULE, width=1)),
            ))
            st.plotly_chart(style_chart(fig, height=260), use_container_width=True)
        else:
            empty_state("No placements recorded yet.")

except Exception as e:
    st.error(f"Couldn't load the overview: {e}")
    st.caption("Check that Docker is running and the database has been seeded.")
