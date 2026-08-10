"""pages/6_revenue_forecast.py — Revenue Forecast"""
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Revenue Forecast", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("📈 Revenue Forecast")
months = st.slider("Forecast months", 3, 24, 12)

with st.spinner("Generating forecast..."):
    from ml.forecaster import forecast_revenue
    df = forecast_revenue(months=months)

fig = go.Figure()
actual   = df[~df["is_forecast"]]
forecast = df[df["is_forecast"]]

fig.add_trace(go.Scatter(x=actual["ds"],   y=actual["yhat"],
    name="Actual", line=dict(color="#0D9488", width=2)))
fig.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat"],
    name="Forecast", line=dict(color="#3B82F6", dash="dash", width=2)))
fig.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat_upper"],
    fill=None, line=dict(color="rgba(59,130,246,0)"), showlegend=False))
fig.add_trace(go.Scatter(x=forecast["ds"], y=forecast["yhat_lower"],
    fill="tonexty", line=dict(color="rgba(59,130,246,0)"),
    fillcolor="rgba(59,130,246,0.15)", name="Confidence band"))
fig.update_layout(title="Monthly Revenue Forecast",
    xaxis_title="Month", yaxis_title="Revenue ($)", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

if not forecast.empty:
    col1, col2, col3 = st.columns(3)
    n = forecast.iloc[0]
    col1.metric("Next Month Forecast", f"${n['yhat']:,.0f}")
    col2.metric("Lower Bound",         f"${n['yhat_lower']:,.0f}")
    col3.metric("Upper Bound",         f"${n['yhat_upper']:,.0f}")

st.download_button("📥 Download forecast CSV",
    df.to_csv(index=False), file_name="revenue_forecast.csv")
