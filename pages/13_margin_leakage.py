"""pages/13_margin_leakage.py — Margin Leakage Analysis"""
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Margin Leakage", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("📊 Margin Leakage")
st.caption("Accounts with below-threshold margins — find and fix revenue leaks.")

threshold = st.slider("Margin threshold (%)", 5, 30, 15,
    help="Accounts below this margin are flagged as leaking")

from ml.anomaly import get_margin_leakage
df = get_margin_leakage(threshold_pct=threshold)

if df.empty:
    st.success(f"✅ No accounts below {threshold}% margin. All accounts are healthy.")
    st.stop()

st.error(f"⚠️ {len(df)} accounts below {threshold}% margin threshold")

# Summary metrics
col1, col2, col3 = st.columns(3)
col1.metric("Leaking Accounts", len(df))

if "avg_margin_pct" in df.columns:
    col2.metric("Worst Margin",  f"{df['avg_margin_pct'].min():.1f}%")
    col3.metric("Avg Margin",    f"{df['avg_margin_pct'].mean():.1f}%")

    # Bar chart
    fig = px.bar(
        df.sort_values("avg_margin_pct"),
        x="client_name" if "client_name" in df.columns else df.columns[1],
        y="avg_margin_pct",
        color="avg_margin_pct",
        color_continuous_scale="RdYlGn",
        range_color=[0, threshold * 1.5],
        title=f"Margin % by Account (threshold: {threshold}%)",
    )
    fig.add_hline(y=threshold, line_dash="dash", line_color="red",
        annotation_text=f"Threshold ({threshold}%)")
    fig.update_layout(xaxis_title="Client", yaxis_title="Margin %")
    st.plotly_chart(fig, use_container_width=True)

st.dataframe(df, use_container_width=True, hide_index=True)
st.download_button("📥 Export CSV", df.to_csv(index=False),
    file_name="margin_leakage.csv")
