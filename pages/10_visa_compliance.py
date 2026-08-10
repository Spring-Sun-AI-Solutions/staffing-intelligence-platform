"""pages/10_visa_compliance.py — Visa Compliance Tracker"""
import streamlit as st

st.set_page_config(page_title="Visa Compliance", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("🛂 Visa Compliance")
st.caption("Active contractors on visa sponsorship — track expiry risks.")

from db.queries import get_candidates
candidates = get_candidates(active_only=True)

visa_types = ["h1b", "opt", "stem_opt", "ead"]
at_risk = candidates[candidates["visa_status"].isin(visa_types)].copy()

col1, col2, col3 = st.columns(3)
col1.metric("Total Active Contractors", len(candidates))
col2.metric("On Visa Sponsorship",      len(at_risk))
col3.metric("Citizen / GC",             len(candidates) - len(at_risk))

if at_risk.empty:
    st.success("No visa-sponsored active contractors found.")
    st.stop()

days_filter = st.selectbox("Risk window", [30, 60, 90, 180],
    index=2, format_func=lambda x: f"Next {x} days")

at_risk["risk_level"] = at_risk["visa_status"].apply(
    lambda v: "🔴 High"   if v in ["opt", "stem_opt"] else
              "🟡 Medium" if v == "ead" else "🟢 Low"
)

st.dataframe(
    at_risk[["name","visa_status","risk_level","location","yoe"]]
    .rename(columns={"name":"Name","visa_status":"Visa","risk_level":"Risk",
                     "location":"Location","yoe":"YOE"}),
    use_container_width=True, hide_index=True,
)
st.info("ℹ️ Connect your HRIS to pull actual visa expiry dates for precise alerts.")
