"""pages/9_recruiter_performance.py — Recruiter Performance KPIs"""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Recruiter KPIs", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("🏆 Recruiter Performance")

days = st.selectbox("Period", [7, 30, 60, 90], index=1,
    format_func=lambda x: f"Last {x} days")

from data.duckdb_client import get_recruiter_kpis
df = get_recruiter_kpis(days=days)

if df.empty:
    st.info("No placement data for this period."); st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Submissions",  int(df["total_submissions"].sum()))
col2.metric("Total Interviews",   int(df["interviews"].sum()))
col3.metric("Total Placements",   int(df["placements"].sum()))
col4.metric("Avg Conversion %",   f"{df['conversion_rate_pct'].mean():.1f}%")

fig = px.bar(df.sort_values("placements", ascending=False),
    x="recruiter_name", y=["total_submissions","interviews","placements"],
    barmode="group", title="Recruiter Activity Breakdown",
    color_discrete_map={"total_submissions":"#94A3B8","interviews":"#3B82F6","placements":"#0D9488"})
fig.update_layout(xaxis_title="Recruiter", yaxis_title="Count", legend_title="Stage")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Leaderboard")
st.dataframe(
    df[["recruiter_name","total_submissions","interviews","placements","conversion_rate_pct"]]
    .rename(columns={"recruiter_name":"Recruiter","total_submissions":"Submissions",
                     "interviews":"Interviews","placements":"Placements",
                     "conversion_rate_pct":"Conversion %"})
    .sort_values("Placements", ascending=False),
    use_container_width=True, hide_index=True,
)
