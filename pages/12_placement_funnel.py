"""pages/12_placement_funnel.py — Placement Funnel Analytics"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Placement Funnel", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("🎯 Placement Funnel")
st.caption("Req → Submission → Interview → Offer → Hire — track conversion at every stage.")

col1, col2 = st.columns(2)
days      = col1.selectbox("Period", [30,60,90,180], index=1,
    format_func=lambda x: f"Last {x} days")
client_id = col2.number_input("Client ID (0 = all clients)", min_value=0, value=0)

from data.duckdb_client import get_placement_funnel
df = get_placement_funnel(
    client_id=int(client_id) if client_id > 0 else None,
    days=days,
)

if df.empty:
    st.info("No placement data for this period."); st.stop()

stage_order  = ["submitted","interview","offer","hire","rejected"]
stage_colors = {"submitted":"#64748B","interview":"#3B82F6","offer":"#F59E0B",
                "hire":"#22C55E","rejected":"#F43F5E"}

df_funnel = df[df["stage"].isin(stage_order)].copy()
df_funnel["stage"] = pd.Categorical(df_funnel["stage"], categories=stage_order, ordered=True)
df_funnel = df_funnel.sort_values("stage")

col1, col2 = st.columns([2, 1])
with col1:
    fig = go.Figure(go.Funnel(
        y=df_funnel["stage"].tolist(),
        x=df_funnel["count"].tolist(),
        textinfo="value+percent initial",
        marker_color=[stage_colors.get(s,"#94A3B8") for s in df_funnel["stage"].tolist()],
    ))
    fig.update_layout(title=f"Placement Funnel — Last {days} days", height=400)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Stage counts")
    if "pct" not in df_funnel.columns:
        total = df_funnel["count"].sum()
        df_funnel["pct"] = (df_funnel["count"] / total * 100).round(1) if total else 0.0

    st.dataframe(df_funnel[["stage", "count", "pct"]]
        .rename(columns={"stage": "Stage", "count": "Count", "pct": "% of Total"}),
        use_container_width=True, hide_index=True)

    total  = df_funnel[df_funnel["stage"]=="submitted"]["count"].sum()
    hired  = df_funnel[df_funnel["stage"]=="hire"]["count"].sum()
    if total > 0:
        st.metric("Overall conversion", f"{hired/total*100:.1f}%",
            help="Hires / Submissions")
