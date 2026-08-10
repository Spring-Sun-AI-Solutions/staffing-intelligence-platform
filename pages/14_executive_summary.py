"""pages/14_executive_summary.py — Executive Summary Dashboard"""
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Executive Summary", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("📋 Executive Summary")
st.caption("High-level platform overview — revenue, placements, margins, and risk.")

# ── KPI row ───────────────────────────────────────────────────────────────────
from db.queries import get_candidates, get_clients, get_placements
candidates = get_candidates()
clients    = get_clients()
placements = get_placements()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Candidates",          len(candidates))
col2.metric("Active Contractors",  int(candidates["is_active_contractor"].sum()))
col3.metric("Clients",             len(clients))
col4.metric("Total Placements",    len(placements))
col5.metric("Hires",               len(placements[placements["stage"]=="hire"]) if not placements.empty else 0)

st.divider()

# ── Revenue forecast + Funnel ─────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📈 Revenue Forecast (6 months)")
    try:
        from ml.forecaster import forecast_revenue
        fc = forecast_revenue(months=6)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fc["ds"], y=fc["yhat"],
            fill="tozeroy", fillcolor="rgba(13,148,136,0.15)",
            line=dict(color="#0D9488"), name="Revenue",
        ))
        fig.update_layout(height=280, margin=dict(l=0,r=0,t=0,b=0),
            showlegend=False, yaxis_title="Revenue ($)")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Forecast unavailable: {e}")

with col2:
    st.subheader("🎯 Placement Funnel (90 days)")
    try:
        from data.duckdb_client import get_placement_funnel
        import pandas as pd
        funnel = get_placement_funnel(days=90)
        stage_order = ["submitted","interview","offer","hire"]
        funnel = funnel[funnel["stage"].isin(stage_order)]
        if not funnel.empty:
            funnel["stage"] = pd.Categorical(funnel["stage"],
                categories=stage_order, ordered=True)
            funnel = funnel.sort_values("stage")
            fig = go.Figure(go.Funnel(
                y=funnel["stage"].tolist(),
                x=funnel["count"].tolist(),
                textinfo="value+percent initial",
                marker_color=["#64748B","#3B82F6","#F59E0B","#22C55E"],
            ))
            fig.update_layout(height=280, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No funnel data available.")
    except Exception as e:
        st.info(f"Funnel unavailable: {e}")

st.divider()

# ── Risk summary ──────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔴 High Churn Risk Clients")
    try:
        from ml.forecaster import predict_client_churn
        import pandas as pd
        results = []
        for _, row in clients.head(10).iterrows():
            r = predict_client_churn(int(row["id"]))
            if r["risk_level"] == "high":
                results.append({"Client": row["name"], "Risk": f"{r['risk_score']*100:.0f}%"})
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        else:
            st.success("No high-risk clients.")
    except Exception as e:
        st.info(f"Churn data unavailable: {e}")

with col2:
    st.subheader("⚠️ High Attrition Risk Contractors")
    try:
        high_risk = candidates[
            candidates["attrition_risk_score"].notna() &
            (candidates["attrition_risk_score"] > 0.6)
        ][["name","attrition_risk_score"]].head(5)
        if not high_risk.empty:
            high_risk.columns = ["Contractor","Risk Score"]
            high_risk["Risk Score"] = high_risk["Risk Score"].round(3)
            st.dataframe(high_risk, use_container_width=True, hide_index=True)
        else:
            st.success("No high attrition risk contractors.")
    except Exception as e:
        st.info(f"Attrition data unavailable: {e}")
