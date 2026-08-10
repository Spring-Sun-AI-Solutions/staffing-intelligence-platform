"""
pages/15_jd_tools.py
Job Description Cleaner & Generator page.
"""
import streamlit as st

st.set_page_config(page_title="JD Tools", layout="wide")

if "username" not in st.session_state:
    st.warning("Please log in from the home page.")
    st.stop()

st.title("✍️ JD Tools")
st.caption("Clean biased job descriptions or generate new ones using AI.")

tab1, tab2 = st.tabs(["🧹 Clean / Improve JD", "✨ Generate JD"])

# ── Tab 1: JD Cleaner ─────────────────────────────────────────────────────────
with tab1:
    st.subheader("Clean & Improve a Job Description")
    raw_jd = st.text_area(
        "Paste your job description here",
        height=300,
        placeholder="Paste the original job description...",
        key="raw_jd",
    )

    if st.button("🧹 Clean JD", type="primary", disabled=not raw_jd.strip()):
        with st.spinner("Analysing and cleaning JD..."):
            try:
                from ml.jd_tools import clean_jd
                result = clean_jd(raw_jd)

                # Bias report
                bias = result.get("bias_report", {})
                bias_score = bias.get("bias_score", 0)
                col1, col2, col3 = st.columns(3)
                col1.metric("Bias Score", f"{bias_score}/10",
                            delta="Lower is better", delta_color="inverse")
                col2.metric("Words Before", result["word_count_before"])
                col3.metric("Words After", result["word_count_after"])

                if bias.get("biased_words"):
                    st.warning(f"⚠️ Biased terms found: {', '.join(bias['biased_words'])}")

                st.divider()
                st.subheader("✅ Cleaned Job Description")
                st.text_area("", value=result["cleaned_jd"], height=400, key="cleaned_output")
                st.download_button("📥 Download cleaned JD", result["cleaned_jd"],
                                   file_name="cleaned_jd.txt")

                if bias.get("suggestions"):
                    with st.expander("💡 Suggestions"):
                        for s in bias["suggestions"]:
                            st.write(f"• {s}")

            except Exception as e:
                st.error(f"❌ Error: {e}")

# ── Tab 2: JD Generator ───────────────────────────────────────────────────────
with tab2:
    st.subheader("Generate a New Job Description")

    col1, col2 = st.columns(2)
    with col1:
        job_title = st.text_input("Job title *", placeholder="e.g. Senior Python Developer")
        location  = st.text_input("Location", value="Remote")
        yoe_min   = st.number_input("Min years experience", min_value=0, max_value=20, value=3)
        yoe_max   = st.number_input("Max years experience", min_value=0, max_value=30, value=8)

    with col2:
        required_skills = st.text_area(
            "Required skills * (one per line)",
            placeholder="Python\nAWS\nDocker\nPostgreSQL",
            height=120,
        )
        nice_to_have = st.text_area(
            "Nice-to-have skills (one per line)",
            placeholder="Kubernetes\nTerraform\nMLflow",
            height=80,
        )
        context = st.text_input("Additional context", placeholder="e.g. Fintech startup, agile team")

    can_generate = job_title.strip() and required_skills.strip()

    if st.button("✨ Generate JD", type="primary", disabled=not can_generate):
        with st.spinner("Generating job description..."):
            try:
                from ml.jd_tools import generate_jd
                required = [s.strip() for s in required_skills.split("\n") if s.strip()]
                nice     = [s.strip() for s in nice_to_have.split("\n") if s.strip()]
                generated = generate_jd(
                    job_title=job_title,
                    required_skills=required,
                    nice_to_have=nice or None,
                    location=location,
                    yoe_min=float(yoe_min),
                    yoe_max=float(yoe_max) if yoe_max > yoe_min else None,
                    additional_context=context,
                )
                st.subheader("📄 Generated Job Description")
                st.text_area("", value=generated, height=500, key="generated_output")
                st.download_button("📥 Download JD", generated,
                                   file_name=f"{job_title.replace(' ', '_')}_jd.txt")
            except Exception as e:
                st.error(f"❌ Error: {e}")
