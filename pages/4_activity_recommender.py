"""pages/4_activity_recommender.py — Recruiter Activity Recommender"""
import streamlit as st

st.set_page_config(page_title="Activity Queue", layout="wide")
if "username" not in st.session_state:
    st.warning("Please log in."); st.stop()

st.title("✅ Activity Recommender")
st.caption("Your priority list for today — jobs to fill, candidates to re-engage, clients to follow up.")

from db.queries import get_open_jobs, get_candidates, get_clients, get_placements
jobs       = get_open_jobs()
candidates = get_candidates()
clients    = get_clients()
placements = get_placements()

col1, col2, col3 = st.columns(3)

# ── Priority jobs ─────────────────────────────────────────────────────────────
with col1:
    st.subheader("🔥 Priority Jobs")
    st.caption("Open reqs with fewest submissions")

    if not jobs.empty and not placements.empty:
        submission_counts = placements.groupby("job_id").size().reset_index(name="submissions")
        jobs_with_counts  = jobs.merge(submission_counts, left_on="id",
            right_on="job_id", how="left").fillna({"submissions": 0})
        priority = jobs_with_counts.sort_values("submissions").head(5)
    else:
        priority = jobs.head(5) if not jobs.empty else None

    if priority is not None and not priority.empty:
        for _, row in priority.iterrows():
            subs = int(row.get("submissions", 0))
            with st.container():
                st.markdown(f"**{row['title']}**")
                st.caption(f"{subs} submissions · Client {row['client_id']}")
                if st.button("🔍 Match candidates", key=f"pjob_{row['id']}",
                             use_container_width=True):
                    st.session_state["selected_job_id"] = row["id"]
                    st.switch_page("pages/1_job_match.py")
    else:
        st.info("No open jobs.")

# ── Candidates to re-engage ───────────────────────────────────────────────────
with col2:
    st.subheader("👤 Re-engage Candidates")
    st.caption("Available candidates not recently submitted")

    if not candidates.empty:
        available = candidates[
            ~candidates["is_active_contractor"] &
            candidates["skills"].apply(lambda x: bool(x))
        ].head(5)
        for _, row in available.iterrows():
            skills_str = ", ".join((row["skills"] or [])[:3])
            with st.container():
                st.markdown(f"**{row['name']}**")
                st.caption(f"{row['visa_status']} · {row['yoe']} yrs · {skills_str}")
                st.markdown("---")
    else:
        st.info("No available candidates.")

# ── Client follow-ups ─────────────────────────────────────────────────────────
with col3:
    st.subheader("📞 Client Follow-ups")
    st.caption("Clients with low req volume or inactivity")

    if not clients.empty:
        follow_up = clients[clients["req_volume"] < 3].head(5)
        for _, row in follow_up.iterrows():
            with st.container():
                st.markdown(f"**{row['name']}**")
                st.caption(f"{row['industry']} · {row['req_volume']} active reqs")
                st.markdown("---")
    else:
        st.info("No clients found.")
