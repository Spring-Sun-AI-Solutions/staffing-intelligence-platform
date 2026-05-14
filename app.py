"""
Staffing Intelligence Platform
Entry point — handles auth gate and role-based navigation.
Run with: streamlit run app.py
"""
import streamlit as st
import yaml
import streamlit_authenticator as stauth
from pathlib import Path

st.set_page_config(
    page_title="Staffing Intelligence Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load user config ──────────────────────────────────────────────────────────
config_path = Path(__file__).parent / "auth_config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

# ── Login ─────────────────────────────────────────────────────────────────────
name, auth_status, username = authenticator.login("Login", "main")

if auth_status is False:
    st.error("Incorrect username or password.")
    st.stop()

if auth_status is None:
    st.info("Please enter your credentials to continue.")
    st.stop()

# ── Authenticated ─────────────────────────────────────────────────────────────
role = config["credentials"]["usernames"][username].get("role", "recruiter")
st.session_state["role"]     = role
st.session_state["username"] = username
st.session_state["name"]     = name

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 🧠 SIP")
    st.markdown(f"**{name}**  \n`{role.upper()}`")
    st.divider()

    # All roles
    st.page_link("pages/1_job_match.py",       label="🔍 Job Match",          )
    st.page_link("pages/2_resume_parser.py",   label="📄 Resume Parser",      )
    st.page_link("pages/5_ai_assistant.py",    label="🤖 AI Assistant",       )

    # Recruiter+
    if role in ("recruiter", "manager", "exec", "compliance"):
        st.page_link("pages/3_attrition_risk.py",      label="⚠️  Attrition Risk",   )
        st.page_link("pages/4_activity_recommender.py",label="✅ Activity Queue",    )

    # Manager+
    if role in ("manager", "exec"):
        st.divider()
        st.page_link("pages/6_revenue_forecast.py",    label="📈 Revenue Forecast",  )
        st.page_link("pages/7_client_churn.py",        label="🔴 Client Churn",      )
        st.page_link("pages/8_rate_optimizer.py",      label="💰 Rate Optimizer",    )
        st.page_link("pages/9_recruiter_performance.py",label="🏆 Recruiter KPIs",  )

    # Exec only
    if role == "exec":
        st.divider()
        st.page_link("pages/12_placement_funnel.py",   label="🎯 Placement Funnel",  )
        st.page_link("pages/13_margin_leakage.py",     label="📊 Margin Leakage",    )
        st.page_link("pages/14_executive_summary.py",  label="📋 Executive Summary", )

    # Compliance only
    if role == "compliance":
        st.divider()
        st.page_link("pages/10_visa_compliance.py",    label="🛂 Visa Compliance",   )
        st.page_link("pages/11_timesheet_anomalies.py",label="🕐 Timesheet Flags",   )

    st.divider()
    authenticator.logout("Logout", "sidebar")

# ── Home landing ──────────────────────────────────────────────────────────────
st.title("🧠 Staffing Intelligence Platform")
st.markdown(f"Welcome back, **{name}**. Use the sidebar to navigate to your module.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Open Reqs",      "—", help="Jobs currently active")
col2.metric("Active Contractors", "—", help="Placed and working")
col3.metric("Submissions MTD","—", help="This month")
col4.metric("Placements MTD", "—", help="This month")

st.info("📦 **Sprint 1 complete.** Data schema coming in Sprint 2 — metrics will populate then.")
