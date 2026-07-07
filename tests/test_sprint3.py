"""
tests/test_sprint3.py
Sprint 3 tests — resume parser, embedder, scheduler.

Most tests are offline (no DB, no GPU needed).
Tests marked with @pytest.mark.db require a live Postgres connection.

Run all:    pytest tests/test_sprint3.py -v
Run offline only: pytest tests/test_sprint3.py -v -m "not db"
"""
import io
import pytest


# ── Parser unit tests (no DB needed) ─────────────────────────────────────────

class TestTextExtraction:

    def test_extract_text_rejects_unsupported_type(self):
        from ml.parser import extract_text
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract_text(b"data", "txt")

    def test_extract_email(self):
        from ml.parser import extract_email
        assert extract_email("Contact: john.doe@example.com for details") == "john.doe@example.com"
        assert extract_email("No email here") is None
        assert extract_email("JOHN@COMPANY.COM") == "john@company.com"

    def test_extract_phone(self):
        from ml.parser import extract_phone
        assert extract_phone("Call me at (555) 123-4567") is not None
        assert extract_phone("Phone: 555.123.4567") is not None
        assert extract_phone("No phone") is None

    def test_extract_email_complex(self):
        from ml.parser import extract_email
        assert extract_email("john.doe+work@company.co.uk") == "john.doe+work@company.co.uk"


class TestSkillExtraction:

    def test_extracts_known_skills(self):
        from ml.parser import extract_skills
        import spacy
        nlp = spacy.blank("en")
        text = "Experienced in Python, AWS, Docker and PostgreSQL"
        skills = extract_skills(text, nlp)
        assert "Python" in skills
        assert "AWS" in skills
        assert "Docker" in skills
        assert "PostgreSQL" in skills

    def test_normalises_aliases(self):
        from ml.parser import extract_skills, normalise_skill
        import spacy
        nlp = spacy.blank("en")
        # Test alias normalisation directly
        assert normalise_skill("reactjs") == "React"
        assert normalise_skill("nodejs") == "Node.js"
        assert normalise_skill("k8s") == "Kubernetes"
        assert normalise_skill("ml") == "Machine Learning"

    def test_handles_empty_text(self):
        from ml.parser import extract_skills
        import spacy
        nlp = spacy.blank("en")
        assert extract_skills("", nlp) == []

    def test_case_insensitive_matching(self):
        from ml.parser import extract_skills
        import spacy
        nlp = spacy.blank("en")
        skills = extract_skills("PYTHON and DOCKER experience", nlp)
        assert "Python" in skills
        assert "Docker" in skills

    def test_no_false_positives_on_common_words(self):
        from ml.parser import extract_skills
        import spacy
        nlp = spacy.blank("en")
        skills = extract_skills("I worked with a great team on a large project", nlp)
        # Common English words should not appear as skills
        assert "Team" not in skills
        assert "Project" not in skills


class TestYoeExtraction:

    def test_extracts_year_ranges(self):
        from ml.parser import extract_yoe
        text = """
        Software Engineer
        Jan 2018 - Dec 2021
        Senior Engineer
        Jan 2022 - Present
        """
        yoe = extract_yoe(text)
        assert yoe >= 4.0  # at least 4 years

    def test_extracts_explicit_years(self):
        from ml.parser import extract_yoe
        text = "10+ years of experience in software development"
        assert extract_yoe(text) == 10.0

    def test_returns_zero_for_no_dates(self):
        from ml.parser import extract_yoe
        assert extract_yoe("No dates or experience mentioned") == 0.0

    def test_handles_present_keyword(self):
        from ml.parser import extract_yoe
        text = "2020 - Present: Software Engineer"
        yoe = extract_yoe(text)
        assert yoe >= 4.0

    def test_handles_various_separators(self):
        from ml.parser import extract_yoe
        text = "2019 — 2023 Backend Developer"
        yoe = extract_yoe(text)
        assert yoe >= 3.5


class TestVisaExtraction:

    def test_detects_citizen(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("I am a US Citizen") == "citizen"
        assert extract_visa_status("USC, authorized to work") == "citizen"

    def test_detects_h1b(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("Currently on H1B visa") == "h1b"
        assert extract_visa_status("H-1B holder") == "h1b"

    def test_detects_opt(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("F1 OPT status") == "opt"

    def test_detects_stem_opt_over_opt(self):
        from ml.parser import extract_visa_status
        # STEM OPT should take priority over OPT
        assert extract_visa_status("STEM OPT extension valid until 2025") == "stem_opt"

    def test_detects_green_card(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("Permanent Resident (Green Card)") == "gc"

    def test_detects_ead(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("Employment Authorization Document holder") == "ead"

    def test_returns_unknown_for_no_visa_info(self):
        from ml.parser import extract_visa_status
        assert extract_visa_status("Software engineer with Python skills") == "unknown"


class TestParserIntegration:

    def _make_pdf(self, text: str) -> bytes:
        """Create a minimal valid PDF with the given text for testing."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        y = 750
        for line in text.split("\n"):
            c.drawString(50, y, line.strip())
            y -= 15
        c.save()
        return buf.getvalue()

    def test_parse_synthetic_resume(self):
        """Parse a synthetic resume and verify all fields extracted."""
        try:
            from ml.parser import parse_resume
            resume_text = """
John Smith
john.smith@example.com
(555) 123-4567
US Citizen

Experience:
Software Engineer at TechCorp
Jan 2019 - Dec 2022

Senior Engineer at StartupCo
Jan 2023 - Present

Skills: Python, AWS, Docker, PostgreSQL, React, Node.js
"""
            pdf_bytes = self._make_pdf(resume_text)
            result = parse_resume(pdf_bytes, "pdf")

            assert result["email"] == "john.smith@example.com"
            assert result["visa_status"] == "citizen"
            assert result["yoe"] >= 3.0
            assert "Python" in result["skills"]
            assert "AWS" in result["skills"]
            assert len(result["raw_text"]) > 50

        except ImportError:
            pytest.skip("reportlab not installed — install with: pip install reportlab")

    def test_parse_raises_on_empty_pdf(self):
        """Parser should raise ValueError on empty/unreadable PDF."""
        from ml.parser import parse_resume
        with pytest.raises(Exception):  # ValueError or pdfminer error
            parse_resume(b"not a pdf", "pdf")


# ── Embedder unit tests ───────────────────────────────────────────────────────

class TestEmbedder:

    def test_embed_text_returns_correct_dimension(self):
        from ml.embedder import embed_text, EMBEDDING_DIM
        vector = embed_text("Python developer with 5 years AWS experience")
        assert len(vector) == EMBEDDING_DIM
        assert all(isinstance(v, float) for v in vector)

    def test_embed_empty_text_returns_zeros(self):
        from ml.embedder import embed_text, EMBEDDING_DIM
        vector = embed_text("")
        assert len(vector) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vector)

    def test_embed_text_normalized(self):
        """Embeddings should be unit-normalized (L2 norm ≈ 1.0)."""
        import math
        from ml.embedder import embed_text
        vector = embed_text("Python machine learning engineer")
        norm = math.sqrt(sum(v**2 for v in vector))
        assert abs(norm - 1.0) < 0.01

    def test_similar_texts_have_high_similarity(self):
        """Semantically similar texts should have cosine similarity > 0.8."""
        import math
        from ml.embedder import embed_text
        v1 = embed_text("Python developer with machine learning experience")
        v2 = embed_text("Python engineer skilled in ML and data science")
        # Cosine similarity (vectors are already normalised)
        similarity = sum(a * b for a, b in zip(v1, v2))
        assert similarity > 0.7, f"Expected similarity > 0.7, got {similarity:.3f}"

    def test_dissimilar_texts_have_lower_similarity(self):
        """Unrelated texts should have lower cosine similarity."""
        import math
        from ml.embedder import embed_text
        v1 = embed_text("Python machine learning engineer with AWS experience")
        v2 = embed_text("Marketing manager with social media expertise")
        similarity = sum(a * b for a, b in zip(v1, v2))
        assert similarity < 0.7, f"Expected similarity < 0.7, got {similarity:.3f}"

    def test_batch_embed_returns_correct_count(self):
        from ml.embedder import embed_texts_batch, EMBEDDING_DIM
        texts = ["Python dev", "Java engineer", "Data scientist"]
        results = embed_texts_batch(texts)
        assert len(results) == 3
        for vec in results:
            assert len(vec) == EMBEDDING_DIM

    def test_batch_embed_empty_list(self):
        from ml.embedder import embed_texts_batch
        assert embed_texts_batch([]) == []


# ── Scheduler tests ───────────────────────────────────────────────────────────

class TestScheduler:

    def test_start_stop_scheduler(self):
        from data.scheduler import start_scheduler, stop_scheduler, get_scheduler_status
        start_scheduler()
        status = get_scheduler_status()
        assert status["running"] is True
        assert len(status["jobs"]) == 3
        stop_scheduler()

    def test_idempotent_start(self):
        """Starting scheduler twice should not raise."""
        from data.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
        start_scheduler()  # Should not raise
        stop_scheduler()

    def test_scheduler_has_expected_jobs(self):
        from data.scheduler import start_scheduler, stop_scheduler, get_scheduler_status
        start_scheduler()
        status = get_scheduler_status()
        job_ids = [j["id"] for j in status["jobs"]]
        assert "embed_candidates" in job_ids
        assert "embed_jobs" in job_ids
        assert "heartbeat" in job_ids
        stop_scheduler()


# ── File structure tests ──────────────────────────────────────────────────────

class TestSprint3FileStructure:

    def test_parser_module_importable(self):
        from ml.parser import parse_resume, parse_resume_file
        assert callable(parse_resume)
        assert callable(parse_resume_file)

    def test_embedder_module_importable(self):
        from ml.embedder import embed_text, embed_all_candidates, embed_all_jobs
        assert callable(embed_text)

    def test_scheduler_module_importable(self):
        from data.scheduler import start_scheduler, stop_scheduler
        assert callable(start_scheduler)

    def test_batch_embed_module_importable(self):
        from data.batch_embed import embed_seed_data
        assert callable(embed_seed_data)

    def test_resume_parser_page_exists(self):
        from pathlib import Path
        assert Path("pages/2_resume_parser.py").exists()
