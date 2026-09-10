"""
pages/1_job_match.py
Rank candidates against an open requisition.

Demonstrates the filter + master/detail drilldown pattern used across the app:
  · Filters live in a bordered bar above the results and persist in session_state
  · Selecting a row reveals the detail panel without leaving the page
  · Every filter change is reflected in the result count
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Job match", page_icon="◧", layout="wide")

from app.theme import (
    apply_theme, page_header, metric_row, badge, section, score_bar,
    skill_chips, detail_rows, empty_state, style_chart, require_auth,
    BRAND, GOOD, WARN, RISK, INK_MUTED, RULE,
)

apply_theme()
require_auth()

from db.queries import get_open_jobs

# ── Job selection ─────────────────────────────────────────────────────────────
jobs = get_open_jobs()

if jobs.empty:
    page_header("Job match")
    empty_state("No open requisitions. Add a job to start matching candidates.")
    st.stop()

job_labels = {f"{r['title']}  ·  req {r['id']}": r["id"] for _, r in jobs.iterrows()}

# Honour a job passed in from another page
preselect = 0
if "selected_job_id" in st.session_state:
    for i, (_, jid) in enumerate(job_labels.items()):
        if jid == st.session_state["selected_job_id"]:
            preselect = i
    del st.session_state["selected_job_id"]

page_header(
    "Job match",
    "Rank candidates against an open requisition and review skill gaps.",
)

selected = st.selectbox("Requisition", list(job_labels), index=preselect,
                        label_visibility="collapsed")
job_id = job_labels[selected]
job    = jobs[jobs["id"] == job_id].iloc[0]

# Job context — what the recruiter is matching against
req_skills = job.get("required_skills") or []
metric_row([
    {"label": "Location",    "value": job.get("location") or "—",
     "note": "remote ok" if job.get("remote_ok") else "on site"},
    {"label": "Rate range",  "value": f"${job.get('rate_min', 0):.0f}–{job.get('rate_max', 0):.0f}",
     "note": "per hour"},
    {"label": "Experience",  "value": f"{job.get('min_yoe', 0):.0f}+ yrs"},
    {"label": "Visa",        "value": (job.get("visa_requirement") or "no restriction")},
    {"label": "Skills",      "value": len(req_skills), "note": "required"},
])

# ── Filters ───────────────────────────────────────────────────────────────────
section("Filters")

f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
min_score = f1.slider("Minimum match", 0, 100, 40, step=5)
visa_pick = f2.selectbox("Visa status",
                         ["Any", "citizen", "gc", "h1b", "opt", "stem_opt", "ead"])
loc_text  = f3.text_input("Location contains", placeholder="e.g. New York")
top_n     = f4.selectbox("Show", [10, 25, 50, 100], index=1)

# ── Run the matcher ───────────────────────────────────────────────────────────
cache_key = f"match_{job_id}_{min_score}_{visa_pick}_{loc_text}_{top_n}"

from data.redis_client import cache_get, cache_set

results = cache_get(cache_key)
from_cache = results is not None

if not from_cache:
    with st.spinner("Scoring candidates…"):
        from ml.matcher import rank_candidates
        results = rank_candidates(
            job_id=job_id,
            top_n=top_n,
            min_score=min_score,
            visa_filter=None if visa_pick == "Any" else visa_pick,
            location_filter=loc_text or None,
        )
        cache_set(cache_key, results, ttl=180)

if not results:
    empty_state(
        "No candidates clear these filters. Try lowering the minimum match "
        "or widening the visa and location criteria."
    )
    st.stop()

# ── Results ───────────────────────────────────────────────────────────────────
strong = sum(1 for r in results if r["match_score"] >= 70)
clean  = sum(1 for r in results if not r["skill_gap"].get("must_missing"))

section(f"{len(results)} matches")

st.markdown(
    f'<div style="font-size:.8rem;color:{INK_MUTED};margin-bottom:.6rem">'
    f'{strong} scoring 70 or above · {clean} with no must-have gaps'
    f'{" · served from cache" if from_cache else ""}</div>',
    unsafe_allow_html=True,
)

# Results table — score bar and badges rendered as HTML for density
rows_html = [
    f'<div style="display:grid;grid-template-columns:2fr 1.4fr 1fr 1.2fr .8fr .8fr;'
    f'gap:.75rem;padding:.5rem .75rem;border-bottom:1px solid {RULE};'
    f'font-size:.75rem;font-weight:600;color:{INK_MUTED}">'
    f'<div>Candidate</div><div>Match</div><div>Visa</div>'
    f'<div>Location</div><div>Exp</div><div>Rate</div></div>'
]

for r in results:
    gap = r["skill_gap"]
    n_missing = len(gap.get("must_missing", []))
    visa_level = {"citizen": "good", "gc": "good", "h1b": "info",
                  "opt": "warn", "stem_opt": "warn", "ead": "info"}.get(
                      r["visa_status"], "mute")
    rows_html.append(
        f'<div style="display:grid;grid-template-columns:2fr 1.4fr 1fr 1.2fr .8fr .8fr;'
        f'gap:.75rem;padding:.55rem .75rem;border-bottom:1px solid #F0F1F3;'
        f'font-size:.85rem;align-items:center">'
        f'<div style="font-weight:500">{r["candidate_name"]}'
        + (f' <span style="color:{RISK};font-size:.75rem">'
           f'{n_missing} gap{"s" if n_missing > 1 else ""}</span>' if n_missing else "")
        + f'</div>'
        f'<div>{score_bar(r["match_score"])}</div>'
        f'<div>{badge(r["visa_status"], visa_level)}</div>'
        f'<div style="color:{INK_MUTED}">{r.get("location") or "—"}</div>'
        f'<div style="font-family:IBM Plex Mono,monospace">{r.get("yoe") or 0:.0f}y</div>'
        f'<div style="font-family:IBM Plex Mono,monospace">'
        f'${r.get("rate") or 0:.0f}</div>'
        f'</div>'
    )

st.markdown(
    f'<div style="border:1px solid {RULE};border-radius:8px;overflow:hidden;'
    f'background:#fff">{"".join(rows_html)}</div>',
    unsafe_allow_html=True,
)

# ── Drilldown ─────────────────────────────────────────────────────────────────
section("Candidate detail")

pick = st.selectbox(
    "Candidate", [r["candidate_name"] for r in results],
    label_visibility="collapsed",
)
cand = next(r for r in results if r["candidate_name"] == pick)

d1, d2 = st.columns([1, 1], gap="large")

with d1:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.5rem">'
        f'Why this score</div>', unsafe_allow_html=True)

    scores = cand["scores"]
    labels = {"semantic": "Profile similarity", "skill": "Skill overlap",
              "visa": "Visa fit", "yoe": "Experience",
              "rate": "Rate fit", "location": "Location"}
    fig = go.Figure(go.Bar(
        x=list(scores.values()),
        y=[labels.get(k, k) for k in scores],
        orientation="h",
        marker_color=[GOOD if v >= 70 else WARN if v >= 45 else RISK
                      for v in scores.values()],
        text=[f"{v:.0f}" for v in scores.values()],
        textposition="outside",
        textfont=dict(size=11),
    ))
    fig.update_xaxes(range=[0, 112], showticklabels=False)
    st.plotly_chart(style_chart(fig, height=230), use_container_width=True)

with d2:
    st.markdown(
        f'<div style="font-size:.8rem;font-weight:600;margin-bottom:.5rem">'
        f'Skills against this req</div>', unsafe_allow_html=True)

    gap = cand["skill_gap"]
    st.markdown(skill_chips(gap.get("present", []), gap.get("missing", [])),
                unsafe_allow_html=True)

    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
    detail_rows([
        ("Overall match", f'{cand["match_score"]:.0f} / 100'),
        ("Visa status",   cand["visa_status"]),
        ("Experience",    f'{cand.get("yoe") or 0:.1f} years'),
        ("Expected rate", f'${cand.get("rate") or 0:.0f}/hr'),
        ("Gap severity",  gap.get("severity", "—")),
    ])

# ── Submission ────────────────────────────────────────────────────────────────
st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
c1, c2 = st.columns([1, 4])

with c1:
    submit = st.button("Submit to client", type="primary", use_container_width=True)

if submit:
    try:
        from db.queries import create_placement
        from ml.predictor import predict_submission_success

        pid = create_placement({
            "candidate_id": cand["candidate_id"],
            "job_id":       int(job_id),
            "client_id":    int(job["client_id"]),
            "match_score":  cand["match_score"],
            "skill_gap":    cand["skill_gap"],
        })
        probs = predict_submission_success(cand["candidate_id"], int(job_id))

        with c2:
            st.markdown(
                f'{badge("SUBMITTED", "good")} '
                f'<span style="font-size:.875rem">{cand["candidate_name"]} '
                f'submitted as placement {pid}. Predicted interview '
                f'{probs["interview"]:.0%}, hire {probs["hire"]:.0%}.</span>',
                unsafe_allow_html=True,
            )
    except Exception as e:
        with c2:
            st.error(f"Submission didn't save: {e}")
