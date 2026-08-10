"""pages/3_attrition_risk.py"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Attrition Risk", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("⚠️ Attrition Risk")
st.caption("Active contractors ranked by exit risk.")

from db.queries import get_candidates
df = get_candidates(active_only=True)

if df.empty:
    st.info("No active contractors found."); st.stop()

# Score any unscored contractors
unscored = df[df["attrition_risk_score"].isna()]
if not unscored.empty:
    with st.spinner(f"Scoring {len(unscored)} contractors..."):
        from ml.predictor import predict_attrition_risk
        for _, row in unscored.iterrows():
            try: predict_attrition_risk(int(row["id"]))
            except Exception: pass
    from db.queries import get_candidates
    df = get_candidates(active_only=True)

df = df.sort_values("attrition_risk_score", ascending=False)
df["risk_level"] = df["attrition_risk_score"].apply(
    lambda x: "🔴 High" if x and x > 0.6 else "🟡 Medium" if x and x > 0.35 else "🟢 Low"
)

risk_filter = st.selectbox("Filter by risk", ["All", "High", "Medium", "Low"])
if risk_filter != "All":
    df = df[df["risk_level"].str.contains(risk_filter)]

display = df[["name", "attrition_risk_score", "risk_level",
              "tenure_days", "comms_gap_days", "overtime_pct",
              "client_feedback_score"]].copy()
display.columns = ["Name", "Risk Score", "Risk Level", "Tenure Days",
                   "Comms Gap", "Overtime %", "Feedback Score"]

st.dataframe(display, use_container_width=True, hide_index=True)
