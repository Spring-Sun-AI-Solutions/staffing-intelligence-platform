"""
pages/14_executive_summary.py
Executive overview — revenue, pipeline, and account health on one screen.

Demonstrates the dashboard pattern:
  · A period filter that drives every panel
  · Panels sized by importance, not equally
  · Each panel links through to its detail page
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Executive summary", page_icon="◧", layout="wide")

from app.theme import (
    apply_theme, page_header, metric_row, badge, section,
    empty_state, style_chart, require_auth,
    BRAND, GOOD, WARN, RISK, INK, INK_MUTED, RULE, SERIES,
)

apply_theme()
require_auth()

from db.queries import get_candidates, get_clients, get_placements

# ── Header + period ───────────────────────────────────────────────────────────
page_header(
    "Executive summary",
    "Revenue, pipeline, and account health across the business.",
)

period = st.radio(
    "Period", [30, 90, 180],
    format_func=lambda d: f"Last {d} days",
    horizontal=True, index=1, label_visibility="collapsed",
)

candidates = get_candidates()
clients    = get_clients()
placements = get_placements()

if placements.empty:
    empty_state("No placement history yet. Submit candidates to populate this view.")
    st.stop()

# Filter to period
placements["submitted_at"] = pd.to_datetime(placements["submitted_at"])
cutoff = pd.Timestamp.now() - pd.Timedelta(days=period)
recent = placements[placements["submitted_at"] >= cutoff]

hires  = len(recent[recent["stage"] == "hire"])
subs   = len(recent)
active = int(candidates["is_active_contractor"].sum()) if not candidates.empty else 0
revenue = recent["bill_rate"].sum() * 40 if "bill_rate" in recent else 0
avg_margin = clients["margin_pct"].mean() if not clients.empty else 0

metric_row([
    {"label": "Submissions",     "value": subs},
    {"label": "Hires",           "value": hires,
     "note": f"{hires / subs * 100:.0f}% conversion" if subs else "—"},
    {"label": "On assignment",   "value": active},
    {"label": "Weekly run rate", "value": f"${revenue:,.0f}"},
    {"label": "Average margin",  "value": f"{avg_margin:.1f}%",
     "delta": f"{avg_margin - 25:+.1f} vs target", "good": avg_margin >= 25},
])

# ── Row 1: revenue trend (wide) + funnel (narrow) ─────────────────────────────
left, right = st.columns([3, 2], gap="large")

with left:
    section("Revenue trajectory")
    try:
        from ml.forecaster import forecast_revenue
        fc = forecast_revenue(months=6)
        actual   = fc[~fc["is_forecast"]]
        forecast = fc[fc["is_forecast"]]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=forecast["ds"], y=forecast["yhat_upper"],
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=forecast["ds"], y=forecast["yhat_lower"],
            fill="tonexty", fillcolor="rgba(15,118,110,.10)",
            line=dict(width=0), name="Range", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=actual["ds"], y=actual["yhat"],
            line=dict(color=BRAND, width=2), name="Actual",
        ))
        fig.add_trace(go.Scatter(
            x=forecast["ds"], y=forecast["yhat"],
            line=dict(color=BRAND, width=2, dash="dot"), name="Forecast",
        ))
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        st.plotly_chart(style_chart(fig, height=300, showlegend=True),
                        use_container_width=True)
    except Exception as e:
        empty_state(f"Forecast unavailable. {e}")

with right:
    section("Pipeline")
    order = ["submitted", "interview", "offer", "hire"]
    counts = (recent[recent["stage"].isin(order)]
              .groupby("stage").size().reindex(order).fillna(0))

    if counts.sum():
        fig = go.Figure(go.Funnel(
            y=[s.title() for s in order],
            x=counts.tolist(),
            textinfo="value+percent initial",
            textfont=dict(size=11),
            marker_color=["#CBD5E1", "#94A3B8", "#0F766E", "#115E59"],
            connector=dict(line=dict(color=RULE, width=1)),
        ))
        st.plotly_chart(style_chart(fig, height=300), use_container_width=True)
        st.page_link("pages/12_placement_funnel.py", label="Funnel detail")
    else:
        empty_state("No placements in this period.")

# ── Row 2: account health ─────────────────────────────────────────────────────
section("Account health")

a1, a2 = st.columns([3, 2], gap="large")

with a1:
    if not clients.empty:
        cl = clients.sort_values("margin_pct")
        colors = [RISK if m < 12 else WARN if m < 20 else GOOD
                  for m in cl["margin_pct"]]
        fig = go.Figure(go.Bar(
            x=cl["margin_pct"], y=cl["name"], orientation="h",
            marker_color=colors,
            text=[f"{m:.0f}%" for m in cl["margin_pct"]],
            textposition="outside", textfont=dict(size=10),
        ))
        fig.add_vline(x=25, line_dash="dot", line_color=INK_MUTED, line_width=1,
                      annotation_text="target", annotation_position="top",
                      annotation_font_size=10)
        fig.update_xaxes(range=[0, max(cl["margin_pct"]) * 1.25],
                         showticklabels=False)
        st.plotly_chart(style_chart(fig, height=max(280, len(cl) * 26)),
                        use_container_width=True)
    else:
        empty_state("No client records.")

with a2:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.6rem">'
        f'Flagged accounts</div>', unsafe_allow_html=True)

    flagged = []
    if not clients.empty:
        for _, c in clients.iterrows():
            reasons = []
            if c["margin_pct"] < 12:
                reasons.append(f"{c['margin_pct']:.0f}% margin")
            if c["req_volume"] == 0:
                reasons.append("no open reqs")
            if c["status"] != "active":
                reasons.append(c["status"])
            if reasons:
                level = "risk" if c["margin_pct"] < 12 else "warn"
                flagged.append((c["name"], ", ".join(reasons), level))

    if flagged:
        for nm, why, lvl in flagged[:8]:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;padding:.4rem 0;'
                f'border-bottom:1px solid #F0F1F3;font-size:.85rem">'
                f'<span style="font-weight:500">{nm}</span>'
                f'{badge(why, lvl)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        st.page_link("pages/13_margin_leakage.py", label="Margin detail")
    else:
        empty_state("All accounts within thresholds.")

# ── Row 3: workforce risk ─────────────────────────────────────────────────────
section("Workforce risk")

w1, w2, w3 = st.columns(3, gap="large")

with w1:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.6rem">'
        f'Attrition exposure</div>', unsafe_allow_html=True)
    if not candidates.empty and "attrition_risk_score" in candidates:
        scored = candidates[candidates["attrition_risk_score"].notna()]
        high = len(scored[scored["attrition_risk_score"] > 0.6])
        med  = len(scored[(scored["attrition_risk_score"] > 0.35)
                          & (scored["attrition_risk_score"] <= 0.6)])
        low  = len(scored) - high - med
        fig = go.Figure(go.Bar(
            x=["High", "Medium", "Low"], y=[high, med, low],
            marker_color=[RISK, WARN, GOOD],
            text=[high, med, low], textposition="outside",
        ))
        fig.update_yaxes(showticklabels=False)
        st.plotly_chart(style_chart(fig, height=200), use_container_width=True)
    else:
        empty_state("Not scored yet.")

with w2:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.6rem">'
        f'Visa mix</div>', unsafe_allow_html=True)
    if not candidates.empty:
        mix = candidates[candidates["is_active_contractor"]]["visa_status"] \
                  .value_counts()
        if len(mix):
            fig = go.Figure(go.Bar(
                x=mix.values, y=[str(i) for i in mix.index], orientation="h",
                marker_color=BRAND, text=mix.values, textposition="outside",
            ))
            fig.update_xaxes(showticklabels=False,
                             range=[0, mix.max() * 1.2])
            st.plotly_chart(style_chart(fig, height=200), use_container_width=True)
        else:
            empty_state("No active contractors.")
    else:
        empty_state("No candidate records.")

with w3:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.6rem">'
        f'Timesheet flags</div>', unsafe_allow_html=True)
    try:
        from db.queries import get_timesheets
        ts = get_timesheets(flagged_only=True)
        total = len(get_timesheets())
        pct = len(ts) / total * 100 if total else 0
        st.markdown(
            f'<div style="font-size:2.2rem;font-weight:600;color:{RISK};'
            f'line-height:1.1">{len(ts)}</div>'
            f'<div style="font-size:.8rem;color:{INK_MUTED};margin-bottom:.8rem">'
            f'{pct:.1f}% of {total} submitted</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/11_timesheet_anomalies.py", label="Review flags")
    except Exception:
        empty_state("Not available.")
