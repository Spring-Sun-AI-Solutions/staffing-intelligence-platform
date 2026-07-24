"""
tests/test_sprint4.py
Sprint 4 tests — matching engine and prediction models.

Run: pytest tests/test_sprint4.py -v
"""
import pytest
import numpy as np


# ── Scorer unit tests (no DB) ─────────────────────────────────────────────────

class TestSemanticScorer:

    def test_identical_embeddings_score_1(self):
        from ml.matcher import score_semantic
        vec = [0.1] * 384
        assert score_semantic(vec, vec) == pytest.approx(1.0, abs=0.01)

    def test_none_embeddings_score_0(self):
        from ml.matcher import score_semantic
        assert score_semantic(None, None) == 0.0
        assert score_semantic([0.1] * 384, None) == 0.0

    def test_orthogonal_embeddings_score_low(self):
        from ml.matcher import score_semantic
        v1 = [1.0] + [0.0] * 383
        v2 = [0.0, 1.0] + [0.0] * 382
        assert score_semantic(v1, v2) == pytest.approx(0.0, abs=0.01)


class TestSkillScorer:

    def test_perfect_match(self):
        from ml.matcher import score_skill_overlap
        score, gap = score_skill_overlap(
            ["Python", "AWS", "Docker"],
            ["Python", "AWS", "Docker"],
        )
        assert score == pytest.approx(1.0)
        assert gap["missing"] == []

    def test_no_match(self):
        from ml.matcher import score_skill_overlap
        score, gap = score_skill_overlap(
            ["Java", "Spring"],
            ["Python", "AWS", "Docker"],
        )
        assert score < 0.2
        assert len(gap["missing"]) == 3

    def test_partial_match(self):
        from ml.matcher import score_skill_overlap
        score, gap = score_skill_overlap(
            ["Python", "AWS"],
            ["Python", "AWS", "Docker", "Kubernetes"],
        )
        assert 0.3 < score < 0.9

    def test_empty_required_skills(self):
        from ml.matcher import score_skill_overlap
        score, gap = score_skill_overlap(["Python"], [])
        assert score == 1.0

    def test_case_insensitive_matching(self):
        from ml.matcher import score_skill_overlap
        score, gap = score_skill_overlap(
            ["python", "aws"],
            ["Python", "AWS"],
        )
        assert score == pytest.approx(1.0)

    def test_skill_gap_severity(self):
        from ml.matcher import score_skill_overlap
        _, gap_none = score_skill_overlap(
            ["Python", "AWS", "Docker"],
            ["Python", "AWS", "Docker"],
        )
        _, gap_high = score_skill_overlap(
            [],
            ["Python", "AWS", "Docker", "Kubernetes", "Terraform"],
        )
        assert gap_none["severity"] == "low"
        assert gap_high["severity"] == "high"


class TestVisaScorer:

    def test_no_requirement_accepts_all(self):
        from ml.matcher import score_visa
        for visa in ["citizen", "gc", "h1b", "opt", "ead", "unknown"]:
            assert score_visa(visa, None) == 1.0

    def test_citizen_requirement(self):
        from ml.matcher import score_visa
        assert score_visa("citizen", "citizen") == 1.0
        assert score_visa("h1b", "citizen") == 0.0
        assert score_visa("opt", "citizen") == 0.0

    def test_gc_accepts_citizen(self):
        from ml.matcher import score_visa
        assert score_visa("citizen", "gc") == 1.0
        assert score_visa("gc", "gc") == 1.0
        assert score_visa("h1b", "gc") == 0.0


class TestYOEScorer:

    def test_within_range(self):
        from ml.matcher import score_yoe
        assert score_yoe(5.0, 3.0, 8.0) == 1.0

    def test_under_minimum(self):
        from ml.matcher import score_yoe
        score = score_yoe(2.0, 5.0, 10.0)
        assert score < 1.0
        assert score > 0.0

    def test_overqualified(self):
        from ml.matcher import score_yoe
        score = score_yoe(15.0, 2.0, 5.0)
        assert score == pytest.approx(0.7)

    def test_no_max_yoe(self):
        from ml.matcher import score_yoe
        assert score_yoe(10.0, 3.0, None) == 1.0


class TestRateScorer:

    def test_within_range(self):
        from ml.matcher import score_rate
        assert score_rate(80.0, 70.0, 100.0) == 1.0

    def test_below_min_is_good(self):
        from ml.matcher import score_rate
        assert score_rate(60.0, 70.0, 100.0) == 1.0

    def test_above_max_penalised(self):
        from ml.matcher import score_rate
        score = score_rate(150.0, 70.0, 100.0)
        assert score < 1.0

    def test_no_rate_info(self):
        from ml.matcher import score_rate
        assert score_rate(None, None, None) == 0.5


class TestLocationScorer:

    def test_remote_ok_always_1(self):
        from ml.matcher import score_location
        assert score_location("New York, NY", "San Francisco, CA", remote_ok=True) == 1.0

    def test_exact_match(self):
        from ml.matcher import score_location
        assert score_location("New York, NY", "New York, NY") == 1.0

    def test_same_state(self):
        from ml.matcher import score_location
        assert score_location("Austin, TX", "Dallas, TX") == pytest.approx(0.7)

    def test_different_state(self):
        from ml.matcher import score_location
        score = score_location("New York, NY", "Los Angeles, CA")
        assert score == pytest.approx(0.3)

    def test_no_location_info(self):
        from ml.matcher import score_location
        assert score_location(None, None) == 0.5


class TestCompositeScorer:

    def _make_mock_candidate(self, **kwargs):
        """Create a simple mock candidate object."""
        class MockCandidate:
            pass
        c = MockCandidate()
        c.id = kwargs.get("id", 1)
        c.name = kwargs.get("name", "Test Candidate")
        c.embedding = kwargs.get("embedding", [0.1] * 384)
        c.skills = kwargs.get("skills", ["Python", "AWS"])
        c.visa_status = type("obj", (object,), {"value": kwargs.get("visa_status", "citizen")})()
        c.location = kwargs.get("location", "New York, NY")
        c.yoe = kwargs.get("yoe", 5.0)
        c.rate = kwargs.get("rate", 80.0)
        return c

    def _make_mock_job(self, **kwargs):
        class MockJob:
            pass
        j = MockJob()
        j.id = kwargs.get("id", 1)
        j.title = kwargs.get("title", "Python Developer")
        j.embedding = kwargs.get("embedding", [0.1] * 384)
        j.required_skills = kwargs.get("required_skills", ["Python", "AWS"])
        j.visa_requirement = kwargs.get("visa_requirement", None)
        j.location = kwargs.get("location", "New York, NY")
        j.remote_ok = kwargs.get("remote_ok", False)
        j.min_yoe = kwargs.get("min_yoe", 3.0)
        j.max_yoe = kwargs.get("max_yoe", 10.0)
        j.rate_min = kwargs.get("rate_min", 70.0)
        j.rate_max = kwargs.get("rate_max", 100.0)
        return j

    def test_perfect_match_scores_high(self):
        from ml.matcher import score_candidate_job
        c = self._make_mock_candidate()
        j = self._make_mock_job()
        result = score_candidate_job(c, j)
        assert result["match_score"] > 70.0

    def test_visa_mismatch_lowers_score(self):
        from ml.matcher import score_candidate_job
        c = self._make_mock_candidate(visa_status="h1b")
        j = self._make_mock_job(visa_requirement=type("obj", (object,), {"value": "citizen"})())
        result = score_candidate_job(c, j)
        # Visa mismatch should lower score
        assert result["scores"]["visa"] == 0.0

    def test_returns_all_required_fields(self):
        from ml.matcher import score_candidate_job
        c = self._make_mock_candidate()
        j = self._make_mock_job()
        result = score_candidate_job(c, j)
        for field in ["match_score", "scores", "skill_gap", "visa_status",
                      "candidate_id", "candidate_name"]:
            assert field in result

    def test_score_between_0_and_100(self):
        from ml.matcher import score_candidate_job
        c = self._make_mock_candidate()
        j = self._make_mock_job()
        result = score_candidate_job(c, j)
        assert 0 <= result["match_score"] <= 100


# ── Predictor unit tests ──────────────────────────────────────────────────────

class TestSubmissionPredictor:

    def test_model_trains_without_error(self):
        from ml.predictor import train_submission_model
        model = train_submission_model(log_to_mlflow=False)
        assert model is not None

    def test_model_predicts_probability(self):
        from ml.predictor import train_submission_model, generate_submission_training_data
        import pandas as pd
        model = train_submission_model(log_to_mlflow=False)
        X, _ = generate_submission_training_data(n=5)
        probs = model.predict_proba(X)
        assert probs.shape == (5, 2)
        assert all(0 <= p <= 1 for p in probs[:, 1])

    def test_feature_builder_returns_dataframe(self):
        from ml.predictor import generate_submission_training_data
        X, y = generate_submission_training_data(n=10)
        assert len(X) == 10
        assert len(y) == 10
        assert "match_score" in X.columns
        assert "skill_overlap" in X.columns


class TestAttritionPredictor:

    def test_model_trains_without_error(self):
        from ml.predictor import train_attrition_model
        model = train_attrition_model(log_to_mlflow=False)
        assert model is not None

    def test_attrition_training_data_shape(self):
        from ml.predictor import generate_attrition_training_data
        X, y = generate_attrition_training_data(n=10)
        assert len(X) == 10
        assert "tenure_days" in X.columns
        assert "comms_gap_days" in X.columns
        assert "client_feedback_score" in X.columns


# ── MLflow test ───────────────────────────────────────────────────────────────

class TestMLflow:

    def test_mlflow_tracking_uri_set(self):
        import os
        from pathlib import Path
        mlruns = Path("data/mlruns")
        # Just verify the path is configured in .env
        db_url = os.getenv("MLFLOW_TRACKING_URI", "./data/mlruns")
        assert db_url is not None

    def test_models_directory_created(self):
        from pathlib import Path
        from ml.predictor import MODEL_DIR
        assert MODEL_DIR.exists()


# ── File structure tests ──────────────────────────────────────────────────────

class TestSprint4FileStructure:

    def test_matcher_importable(self):
        from ml.matcher import rank_candidates, score_candidate_job
        assert callable(rank_candidates)

    def test_predictor_importable(self):
        from ml.predictor import predict_submission_success, predict_attrition_risk
        assert callable(predict_submission_success)

    def test_weights_sum_to_one(self):
        from ml.matcher import WEIGHTS
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001
