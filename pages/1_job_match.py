"""pages/1_job_match.py — Candidate–Job Matching Engine UI"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Job Match", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in.")
    st.stop()

st.title("🔍 Job Match")
st.caption("Select a job to see ranked candidates with match scores and skill gaps.")

# ── Load jobs ─────────────────────────────────────────────────────────────────
from db.queries import get_open_jobs
jobs_df = get_open_jobs()

if jobs_df.empty:
    st.info("No open jobs found. Add jobs via the database.")
    st.stop()

job_options = {f"{row['title']} (ID: {row['id']})": row['id']
               for _, row in jobs_df.iterrows()}
selected_label = st.selectbox("Select a job", list(job_options.keys()))
job_id = job_options[selected_label]

col1, col2, col3 = st.columns(3)
min_score   = col1.slider("Min match score", 0, 100, 0)
visa_filter = col2.selectbox("Visa filter", ["All", "citizen", "gc", "h1b", "opt", "ead"])
top_n       = col3.selectbox("Show top N", [10, 25, 50, 100], index=1)

# ── Run matching ──────────────────────────────────────────────────────────────
cache_key = f"match_{job_id}_{min_score}_{visa_filter}_{top_n}"
from data.redis_client import cache_get, cache_set
cached = cache_get(cache_key)

if cached:
    results = cached
    st.caption("⚡ Loaded from cache")
else:
    with st.spinner("Ranking candidates..."):
        from ml.matcher import rank_candidates
        results = rank_candidates(
            job_id=job_id, top_n=top_n, min_score=min_score,
            visa_filter=None if visa_filter == "All" else visa_filter,
        )
        cache_set(cache_key, results, ttl=180)

if not results:
    st.warning("No candidates match this job with the current filters.")
    st.stop()

st.success(f"Found **{len(results)}** matching candidates")

# ── Results table ─────────────────────────────────────────────────────────────
df = pd.DataFrame(results)
display_df = df[["candidate_name", "match_score", "visa_status", "location", "yoe", "rate"]].copy()
display_df.columns = ["Name", "Match Score", "Visa", "Location", "YOE", "Rate ($/hr)"]
display_df["Match Score"] = display_df["Match Score"].apply(lambda x: f"{x:.1f}")

st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── Candidate detail ──────────────────────────────────────────────────────────
st.divider()
selected_name = st.selectbox("View candidate detail", [r["candidate_name"] for r in results])
selected = next(r for r in results if r["candidate_name"] == selected_name)

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Score breakdown")
    scores = selected["scores"]
    fig = go.Figure(go.Bar(
        x=list(scores.values()), y=list(scores.keys()),
        orientation="h",
        marker_color=["#0D9488" if v >= 70 else "#F59E0B" if v >= 40 else "#F43F5E"
                      for v in scores.values()],
    ))
    fig.update_layout(xaxis_range=[0, 100], height=300, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🛠 Skill gap")
    gap = selected.get("skill_gap", {})
    if gap.get("present"):
        st.markdown("**✅ Present:**")
        st.markdown(" ".join(f"`{s}`" for s in gap["present"]))
    if gap.get("missing"):
        severity_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(gap.get("severity", "low"), "⚪")
        st.markdown(f"**{severity_color} Missing ({gap.get('severity', 'N/A')}):**")
        st.markdown(" ".join(f"`{s}`" for s in gap["missing"]))
    if not gap.get("missing"):
        st.success("No skill gaps — perfect match!")

# ── Submission button ─────────────────────────────────────────────────────────
if st.button("📤 Submit to client", type="primary"):
    try:
        from db.queries import create_placement
        from ml.predictor import predict_submission_success
        placement_id = create_placement({
            "candidate_id": selected["candidate_id"],
            "job_id":       job_id,
            "client_id":    jobs_df[jobs_df["id"] == job_id]["client_id"].values[0],
            "match_score":  selected["match_score"],
            "skill_gap":    selected["skill_gap"],
        })
        probs = predict_submission_success(selected["candidate_id"], job_id)
        st.success(f"✅ Submitted! Placement #{placement_id}")
        st.info(f"Predicted: Interview {probs['interview']*100:.0f}% | "
                f"Hire {probs['hire']*100:.0f}%")
    except Exception as e:
        st.error(f"Submission failed: {e}")
