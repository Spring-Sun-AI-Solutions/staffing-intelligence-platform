"""
tests/test_sprint6.py
Sprint 6 tests — LLM client, JD tools, assistant.

Most tests are offline (mock Ollama).
Tests marked @pytest.mark.ollama require Ollama running locally.

Run offline: pytest tests/test_sprint6.py -v -m "not ollama"
Run all:     pytest tests/test_sprint6.py -v
"""
import pytest
from unittest.mock import patch, MagicMock


# ── LLM client tests ──────────────────────────────────────────────────────────

class TestLLMClient:

    def test_health_check_returns_dict(self):
        from ml.llm_client import health_check
        result = health_check()
        assert isinstance(result, dict)
        assert "available" in result
        assert "model_ready" in result

    def test_health_check_when_ollama_down(self):
        from ml.llm_client import health_check
        with patch("httpx.get", side_effect=Exception("Connection refused")):
            result = health_check()
            assert result["available"] is False
            assert result["model_ready"] is False

    @pytest.mark.ollama
    def test_chat_returns_string(self):
        from ml.llm_client import chat
        response = chat("Say hello in one word")
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.ollama
    def test_chat_with_system_prompt(self):
        from ml.llm_client import chat
        response = chat(
            "What is 2+2?",
            system="You are a math tutor. Answer with just the number.",
        )
        assert "4" in response

    def test_chat_retries_on_timeout(self):
        from ml.llm_client import chat
        call_count = 0
        import httpx

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("timeout")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "message": {"content": "Hello!"}
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch("httpx.post", side_effect=mock_post):
            response = chat("Hello")
            assert response == "Hello!"
            assert call_count == 2  # Failed once, succeeded on retry

    def test_stream_chat_yields_strings(self):
        from ml.llm_client import stream_chat
        import json

        chunks = [
            json.dumps({"message": {"content": "Hello"}, "done": False}).encode(),
            json.dumps({"message": {"content": " world"}, "done": True}).encode(),
        ]

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_lines = MagicMock(return_value=
            [c.decode() for c in chunks])

        with patch("httpx.stream", return_value=mock_response):
            result = list(stream_chat("Say hello"))
            assert "Hello" in result
            assert " world" in result


# ── JD tools tests ────────────────────────────────────────────────────────────

class TestJDTools:

    SAMPLE_JD = """
    We are looking for a rockstar Python ninja developer!
    Must have 10+ years experience (we're a young team).
    Must be a culture fit. Must be able to work long hours.
    Required: Python, AWS. Nice to have: Docker.
    Bachelor's degree required. Must be a US citizen.
    """

    def test_check_bias_returns_dict(self):
        from ml.jd_tools import check_bias
        mock_response = '{"biased_words": ["rockstar", "ninja"], "suggestions": ["developer", "engineer"], "bias_score": 7, "summary": "Highly biased JD"}'
        with patch("ml.jd_tools.chat", return_value=mock_response):
            result = check_bias(self.SAMPLE_JD)
            assert "bias_score" in result
            assert "biased_words" in result

    def test_check_bias_handles_invalid_json(self):
        from ml.jd_tools import check_bias
        with patch("ml.jd_tools.chat", return_value="Not valid JSON"):
            result = check_bias(self.SAMPLE_JD)
            assert result["bias_score"] == 0  # fallback

    def test_clean_jd_returns_dict(self):
        from ml.jd_tools import clean_jd
        mock_cleaned = "We are seeking an experienced Python Developer..."
        mock_bias = '{"biased_words": ["rockstar"], "suggestions": [], "bias_score": 3, "summary": "Slightly biased"}'
        with patch("ml.jd_tools.chat", side_effect=[mock_bias, mock_cleaned]):
            result = clean_jd(self.SAMPLE_JD)
            assert "cleaned_jd" in result
            assert "word_count_before" in result
            assert "word_count_after" in result

    def test_clean_jd_rejects_empty_input(self):
        from ml.jd_tools import clean_jd
        with pytest.raises(ValueError):
            clean_jd("")

    def test_generate_jd_returns_string(self):
        from ml.jd_tools import generate_jd
        mock_jd = "We are looking for a Senior Python Developer with 5+ years..."
        with patch("ml.jd_tools.chat", return_value=mock_jd):
            result = generate_jd("Senior Python Developer", ["Python", "AWS", "Docker"])
            assert isinstance(result, str)
            assert len(result) > 50

    def test_summarise_jd_returns_string(self):
        from ml.jd_tools import summarise_jd
        mock_summary = "Seeking a Python developer with AWS experience for a remote role."
        with patch("ml.jd_tools.chat", return_value=mock_summary):
            result = summarise_jd(self.SAMPLE_JD)
            assert isinstance(result, str)
            assert len(result) > 20

    @pytest.mark.ollama
    def test_generate_jd_live(self):
        from ml.jd_tools import generate_jd
        result = generate_jd(
            "Python Developer",
            ["Python", "AWS"],
            location="Remote",
            yoe_min=3.0,
        )
        assert len(result) > 100
        assert "Python" in result

    @pytest.mark.ollama
    def test_clean_jd_live(self):
        from ml.jd_tools import clean_jd
        result = clean_jd(self.SAMPLE_JD)
        assert len(result["cleaned_jd"]) > 50
        assert "bias_report" in result


# ── Assistant tests ───────────────────────────────────────────────────────────

class TestAssistant:

    def test_ask_returns_dict_structure(self):
        from ml.assistant import ask
        mock_response = MagicMock()
        mock_response.__str__ = lambda self: "John Smith is available with Python skills."
        mock_response.source_nodes = []

        with patch("ml.assistant._get_index") as mock_idx:
            mock_engine = MagicMock()
            mock_engine.query.return_value = mock_response
            mock_idx.return_value.as_query_engine.return_value = mock_engine
            result = ask("Who has Python skills?")

        assert "answer" in result
        assert "sources" in result
        assert "confidence" in result

    def test_ask_handles_no_index(self):
        from ml.assistant import ask
        with patch("ml.assistant._get_index", return_value=None):
            result = ask("test question")
            assert result["confidence"] == "low"
            assert "not available" in result["answer"].lower()

    def test_build_candidate_documents(self):
        from ml.assistant import _build_candidate_documents
        import pandas as pd
        mock_df = pd.DataFrame([{
            "id": 1, "name": "John Smith", "email": "john@test.com",
            "visa_status": "citizen", "location": "New York, NY",
            "yoe": 5.0, "rate": 80.0, "skills": ["Python", "AWS"],
            "is_active_contractor": True, "attrition_risk_score": 0.2,
        }])
        with patch("ml.assistant.get_candidates", return_value=mock_df):
            docs = _build_candidate_documents()
            assert len(docs) == 1
            assert "John Smith" in docs[0].text
            assert "Python" in docs[0].text

    def test_build_job_documents(self):
        from ml.assistant import _build_job_documents
        import pandas as pd
        mock_df = pd.DataFrame([{
            "id": 1, "title": "Python Developer", "client_id": 1,
            "location": "Remote", "remote_ok": True,
            "required_skills": ["Python", "AWS"], "rate_min": 80,
            "rate_max": 110, "min_yoe": 3, "status": "open",
        }])
        with patch("ml.assistant.get_open_jobs", return_value=mock_df):
            docs = _build_job_documents()
            assert len(docs) == 1
            assert "Python Developer" in docs[0].text

    @pytest.mark.ollama
    def test_ask_live_question(self):
        from ml.assistant import ask, build_index
        build_index(force=False)
        result = ask("What candidates are available?")
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 10


# ── File structure tests ──────────────────────────────────────────────────────

class TestSprint6FileStructure:

    def test_llm_client_importable(self):
        from ml.llm_client import chat, stream_chat, health_check
        assert callable(chat)
        assert callable(stream_chat)

    def test_jd_tools_importable(self):
        from ml.jd_tools import clean_jd, generate_jd, summarise_jd
        assert callable(clean_jd)
        assert callable(generate_jd)

    def test_assistant_importable(self):
        from ml.assistant import ask, build_index, stream_answer
        assert callable(ask)
        assert callable(build_index)

    def test_ai_assistant_page_exists(self):
        from pathlib import Path
        assert Path("pages/5_ai_assistant.py").exists()

    def test_jd_tools_page_exists(self):
        from pathlib import Path
        assert Path("pages/15_jd_tools.py").exists()

    def test_index_storage_dir_created(self):
        from pathlib import Path
        assert Path("data/index").exists()
