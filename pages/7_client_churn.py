"""pages/7_client_churn.py — Client Churn Risk"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Client Churn", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("🔴 Client Churn Risk")
st.caption("Clients ranked by likelihood of reducing spend or leaving.")

from db.queries import get_clients
from ml.forecaster import predict_client_churn

clients = get_clients()
if clients.empty:
    st.info("No clients found."); st.stop()

results = []
with st.spinner("Scoring all clients..."):
    for _, row in clients.iterrows():
        try:
            r = predict_client_churn(int(row["id"]))
            results.append({
                "Client":     row["name"],
                "Industry":   row["industry"],
                "Risk Score": f"{r['risk_score']*100:.0f}%",
                "Risk Level": {"high":"🔴 High","medium":"🟡 Medium","low":"🟢 Low"}.get(r["risk_level"],"⚪"),
                "Signals":    ", ".join(r["signals"]) or "None",
            })
        except Exception as e:
            results.append({"Client": row["name"], "Industry": row.get("industry",""),
                "Risk Score":"N/A","Risk Level":"⚪","Signals":str(e)})

df = pd.DataFrame(results)
high = len(df[df["Risk Level"].str.contains("High")])
med  = len(df[df["Risk Level"].str.contains("Medium")])

col1, col2, col3 = st.columns(3)
col1.metric("Total Clients",  len(df))
col2.metric("🔴 High Risk",   high)
col3.metric("🟡 Medium Risk", med)

st.dataframe(df, use_container_width=True, hide_index=True)
