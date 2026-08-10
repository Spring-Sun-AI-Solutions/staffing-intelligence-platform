"""pages/11_timesheet_anomalies.py — Timesheet Anomaly Detection"""
import streamlit as st

st.set_page_config(page_title="Timesheet Flags", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("🕐 Timesheet Anomalies")
st.caption("AI-detected suspicious timesheet entries — duplicate hours, unusual overtime, billing anomalies.")

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Run Detection", type="primary"):
        with st.spinner("Running Isolation Forest anomaly detector..."):
            from ml.anomaly import detect_timesheet_anomalies
            flagged = detect_timesheet_anomalies(flag_in_db=True)
        if flagged.empty:
            st.success("✅ No anomalies detected.")
        else:
            st.session_state["anomaly_results"] = flagged.to_dict("records")
            st.rerun()

# Show existing flagged timesheets from DB
from db.queries import get_timesheets
flagged_db = get_timesheets(flagged_only=True)

if "anomaly_results" in st.session_state:
    import pandas as pd
    flagged_df = pd.DataFrame(st.session_state["anomaly_results"])
    st.warning(f"⚠️ {len(flagged_df)} anomalies detected in latest run")
elif not flagged_db.empty:
    flagged_df = flagged_db
    st.warning(f"⚠️ {len(flagged_df)} flagged timesheets in database")
else:
    st.info("No flagged timesheets. Click **Run Detection** to scan.")
    st.stop()

# Display with action buttons
cols = ["id","contractor_id","week_start","hours","overtime_hours","anomaly_score","anomaly_reason"]
available = [c for c in cols if c in flagged_df.columns]
st.dataframe(flagged_df[available].round(3), use_container_width=True, hide_index=True)

severity_counts = flagged_df["anomaly_score"].apply(
    lambda x: "High" if x and x > 0.7 else "Medium"
).value_counts()
col1, col2 = st.columns(2)
col1.metric("🔴 High severity", severity_counts.get("High", 0))
col2.metric("🟡 Medium severity", severity_counts.get("Medium", 0))
