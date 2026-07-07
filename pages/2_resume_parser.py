"""
pages/2_resume_parser.py
Resume Parser & Skill Extraction page.

Recruiter uploads a PDF or DOCX resume →
  → text extracted
  → skills, visa, YOE parsed
  → embedding generated
  → candidate record created or updated in DB
"""
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Resume Parser", layout="wide")

# ── Auth gate ─────────────────────────────────────────────────────────────────
if "username" not in st.session_state:
    st.warning("Please log in from the home page.")
    st.stop()

st.title("📄 Resume Parser")
st.caption("Upload a PDF or DOCX resume to extract structured candidate data.")

# ── Upload ────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload resume",
    type=["pdf", "docx"],
    help="Supports PDF and DOCX formats. Max 10MB.",
)

if not uploaded:
    st.info("👆 Upload a resume to get started.")
    st.stop()

# ── Parse ─────────────────────────────────────────────────────────────────────
with st.spinner("Parsing resume..."):
    try:
        from ml.parser import parse_resume
        file_bytes = uploaded.read()
        file_type  = Path(uploaded.name).suffix.lstrip(".")
        result     = parse_resume(file_bytes, file_type)
    except Exception as e:
        st.error(f"❌ Failed to parse resume: {e}")
        st.stop()

# ── Display results ───────────────────────────────────────────────────────────
st.success("✅ Resume parsed successfully")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("👤 Candidate info")
    st.text_input("Name",         value=result["name"],        key="r_name")
    st.text_input("Email",        value=result["email"] or "", key="r_email")
    st.text_input("Phone",        value=result["phone"] or "", key="r_phone")
    st.number_input("Years of experience", value=float(result["yoe"]),
                    min_value=0.0, max_value=50.0, step=0.5, key="r_yoe")

    visa_options = ["unknown", "citizen", "gc", "h1b", "opt", "stem_opt", "ead"]
    visa_index = visa_options.index(result["visa_status"]) if result["visa_status"] in visa_options else 0
    st.selectbox("Visa status", options=visa_options, index=visa_index, key="r_visa")

with col2:
    st.subheader(f"🛠 Skills detected ({len(result['skills'])})")
    if result["skills"]:
        # Display as colored tags
        tags_html = " ".join(
            f'<span style="background:#E1F5EE;color:#085041;padding:3px 10px;'
            f'border-radius:20px;font-size:13px;margin:3px;display:inline-block">'
            f'{skill}</span>'
            for skill in result["skills"]
        )
        st.markdown(tags_html, unsafe_allow_html=True)
    else:
        st.warning("No skills detected. The resume may be image-based or have unusual formatting.")

# ── Raw text expander ─────────────────────────────────────────────────────────
with st.expander("📝 View extracted raw text"):
    st.text_area("Raw text", value=result["raw_text"][:3000], height=300, disabled=True)

# ── Save to database ──────────────────────────────────────────────────────────
st.divider()
st.subheader("💾 Save candidate to database")

rate = st.number_input("Expected rate ($/hr)", min_value=0.0, max_value=500.0,
                        step=5.0, value=0.0, key="r_rate")
location = st.text_input("Location", value="", placeholder="e.g. New York, NY or Remote",
                           key="r_location")

if st.button("💾 Save & generate embedding", type="primary"):
    with st.spinner("Saving candidate and generating embedding..."):
        try:
            from data.file_store import save_upload
            from db.queries import create_candidate
            from db.models import VisaStatusEnum
            from ml.embedder import embed_candidate

            # Save file to disk
            uploaded.seek(0)
            resume_path = save_upload(uploaded, subfolder="resumes")

            # Map visa string → enum
            visa_map = {v.value: v for v in VisaStatusEnum}
            visa_enum = visa_map.get(st.session_state.r_visa, VisaStatusEnum.unknown)

            # Create candidate record
            candidate_id = create_candidate({
                "name":        st.session_state.r_name,
                "email":       st.session_state.r_email or None,
                "phone":       st.session_state.r_phone or None,
                "skills":      result["skills"],
                "visa_status": visa_enum,
                "yoe":         st.session_state.r_yoe,
                "rate":        rate or None,
                "location":    location or None,
                "resume_path": resume_path,
                "resume_text": result["raw_text"],
            })

            # Generate and store embedding
            embed_candidate(candidate_id)

            st.success(f"✅ Candidate saved (ID: #{candidate_id}) with embedding generated.")
            st.balloons()

        except Exception as e:
            st.error(f"❌ Failed to save: {e}")
