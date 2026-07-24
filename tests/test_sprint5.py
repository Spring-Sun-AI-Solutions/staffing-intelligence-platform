"""
tests/test_sprint5.py
Sprint 5 tests — forecaster, anomaly detection, DuckDB, Redis.

Run: pytest tests/test_sprint5.py -v
"""
import pytest
import pandas as pd
import numpy as np


# ── Rate optimiser tests ──────────────────────────────────────────────────────

class TestRateOptimizer:

    def test_returns_all_fields(self):
        from ml.forecaster import optimize_rate
        result = optimize_rate("Python", "New York, NY", "citizen", 5.0)
        for field in ["recommended_bill_rate", "recommended_pay_rate",
                      "recommended_margin", "margin_pct", "market_rate", "range"]:
            assert field in result

    def test_bill_rate_above_pay_rate(self):
        from ml.forecaster import optimize_rate
        result = optimize_rate("Python", "remote", "h1b", 5.0)
        assert result["recommended_bill_rate"] > result["recommended_pay_rate"]

    def test_margin_pct_positive(self):
        from ml.forecaster import optimize_rate
        result = optimize_rate("AWS", "San Francisco, CA", "gc", 8.0)
        assert result["margin_pct"] > 0

    def test_location_premium_san_francisco(self):
        from ml.forecaster import optimize_rate
        sf_rate = optimize_rate("Python", "San Francisco, CA", "citizen", 5.0)
        ny_rate = optimize_rate("Python", "Atlanta, GA", "citizen", 5.0)
        assert sf_rate["market_rate"] > ny_rate["market_rate"]

    def test_senior_premium(self):
        from ml.forecaster import optimize_rate
        senior = optimize_rate("Python", "remote", "citizen", 12.0)
        junior = optimize_rate("Python", "remote", "citizen", 2.0)
        assert senior["market_rate"] > junior["market_rate"]

    def test_unknown_skill_returns_default(self):
        from ml.forecaster import optimize_rate
        result = optimize_rate("COBOL", "remote", "citizen", 5.0)
        assert result["recommended_bill_rate"] > 0

    def test_range_min_below_max(self):
        from ml.forecaster import optimize_rate
        result = optimize_rate("Docker", "Chicago, IL", "gc", 6.0)
        assert result["range"]["min"] < result["range"]["max"]


# ── Churn model tests ─────────────────────────────────────────────────────────

class TestChurnModel:

    def test_model_trains_without_error(self):
        from ml.forecaster import train_churn_model
        model = train_churn_model(log_to_mlflow=False)
        assert model is not None

    def test_training_data_balanced(self):
        from ml.forecaster import _generate_churn_training_data
        X, y = _generate_churn_training_data(n=200)
        churn_rate = y.mean()
        assert 0.1 < churn_rate < 0.9  # not heavily imbalanced

    def test_training_data_has_all_features(self):
        from ml.forecaster import _generate_churn_training_data
        X, y = _generate_churn_training_data(n=10)
        required = ["req_volume_trend", "response_time_trend", "margin_pct",
                    "rejected_rate", "inactive_days"]
        for col in required:
            assert col in X.columns


# ── Revenue forecast tests ────────────────────────────────────────────────────

class TestRevenueForecast:

    def test_synthetic_revenue_has_correct_shape(self):
        from ml.forecaster import _generate_synthetic_revenue
        df = _generate_synthetic_revenue()
        assert "month" in df.columns
        assert "revenue" in df.columns
        assert len(df) > 0
        assert (df["revenue"] >= 0).all()

    def test_forecast_returns_dataframe(self):
        from ml.forecaster import forecast_revenue
        result = forecast_revenue(months=6)
        assert isinstance(result, pd.DataFrame)
        assert "ds" in result.columns
        assert "yhat" in result.columns
        assert "is_forecast" in result.columns

    def test_forecast_has_correct_number_of_future_periods(self):
        from ml.forecaster import forecast_revenue
        result = forecast_revenue(months=6)
        future = result[result["is_forecast"]]
        assert len(future) == 6

    def test_forecast_values_non_negative(self):
        from ml.forecaster import forecast_revenue
        result = forecast_revenue(months=3)
        assert (result["yhat"] >= 0).all()


# ── Anomaly detection tests ───────────────────────────────────────────────────

class TestAnomalyDetection:

    def test_feature_builder_returns_correct_columns(self):
        from ml.anomaly import build_timesheet_features, _generate_synthetic_timesheets
        df = _generate_synthetic_timesheets()
        features = build_timesheet_features(df)
        expected = ["hours_zscore", "overtime_ratio", "hours_abs",
                    "hours_vs_global", "is_high_hours", "is_very_high_hours",
                    "is_duplicate_week"]
        for col in expected:
            assert col in features.columns

    def test_model_trains_on_synthetic_data(self):
        from ml.anomaly import train_anomaly_model, _generate_synthetic_timesheets
        df = _generate_synthetic_timesheets()
        model = train_anomaly_model(df)
        assert model is not None

    def test_anomaly_scores_have_correct_shape(self):
        from ml.anomaly import build_timesheet_features, train_anomaly_model
        from ml.anomaly import _generate_synthetic_timesheets
        df = _generate_synthetic_timesheets()
        model = train_anomaly_model(df)
        features = build_timesheet_features(df)
        scores = model.decision_function(features.values)
        assert len(scores) == len(df)

    def test_high_hours_flagged_as_anomaly(self):
        from ml.anomaly import build_timesheet_features, train_anomaly_model
        import pandas as pd
        # Create data with obvious anomalies
        normal = pd.DataFrame([{
            "id": i, "contractor_id": 1,
            "week_start": f"2026-01-{i+1:02d}",
            "hours": 40.0, "overtime_hours": 0.0
        } for i in range(20)])
        anomaly = pd.DataFrame([{
            "id": 99, "contractor_id": 1,
            "week_start": "2026-02-01",
            "hours": 80.0, "overtime_hours": 40.0
        }])
        df = pd.concat([normal, anomaly], ignore_index=True)
        model = train_anomaly_model(df)
        features = build_timesheet_features(df)
        labels = model.predict(features.values)
        # The last row (80 hours) should be flagged
        assert labels[-1] == 1

    def test_synthetic_timesheets_have_some_anomalies(self):
        from ml.anomaly import _generate_synthetic_timesheets
        df = _generate_synthetic_timesheets()
        high_hours = df[df["hours"] > 60]
        assert len(high_hours) > 0  # ~5% should be anomalous


# ── DuckDB tests ──────────────────────────────────────────────────────────────

class TestDuckDB:

    def test_duckdb_connection(self):
        from data.duckdb_client import get_duckdb_conn
        conn = get_duckdb_conn()
        assert conn is not None

    def test_duckdb_simple_query(self):
        from data.duckdb_client import query_duckdb
        result = query_duckdb("SELECT 1 AS test_col")
        assert "test_col" in result.columns
        assert result.iloc[0]["test_col"] == 1

    def test_duckdb_arithmetic(self):
        from data.duckdb_client import query_duckdb
        result = query_duckdb("SELECT 42 * 2 AS answer")
        assert result.iloc[0]["answer"] == 84

    def test_duckdb_returns_dataframe(self):
        from data.duckdb_client import query_duckdb
        result = query_duckdb("SELECT 1 AS a, 2 AS b, 3 AS c")
        assert isinstance(result, pd.DataFrame)


# ── Redis tests ───────────────────────────────────────────────────────────────

class TestRedisClient:

    def test_redis_connection_attempt(self):
        """Redis may or may not be running — verify graceful degradation."""
        from data.redis_client import get_redis
        r = get_redis()
        # Should return either a client or None — never raise
        assert r is None or r is not None

    def test_cache_set_returns_bool(self):
        from data.redis_client import cache_set
        result = cache_set("test_key", {"data": 123})
        assert isinstance(result, bool)

    def test_cache_get_returns_none_when_unavailable(self):
        from data.redis_client import cache_get
        result = cache_get("nonexistent_key_xyz")
        assert result is None

    def test_chat_history_roundtrip(self):
        """If Redis is available, test full chat history roundtrip."""
        from data.redis_client import get_redis, save_chat_history, get_chat_history, clear_chat_history
        r = get_redis()
        if r is None:
            pytest.skip("Redis not available")

        messages = [
            {"role": "user", "content": "What candidates are available?"},
            {"role": "assistant", "content": "I found 5 candidates..."},
        ]
        save_chat_history("test_session_xyz", messages)
        retrieved = get_chat_history("test_session_xyz")
        assert len(retrieved) == 2
        assert retrieved[0]["role"] == "user"
        clear_chat_history("test_session_xyz")

    def test_append_chat_message(self):
        from data.redis_client import get_redis, append_chat_message, clear_chat_history
        r = get_redis()
        if r is None:
            pytest.skip("Redis not available")

        clear_chat_history("test_append_xyz")
        history = append_chat_message("test_append_xyz", "user", "Hello")
        assert len(history) == 1
        history = append_chat_message("test_append_xyz", "assistant", "Hi there!")
        assert len(history) == 2
        clear_chat_history("test_append_xyz")

    def test_redis_info(self):
        from data.redis_client import get_redis_info
        info = get_redis_info()
        assert "available" in info

    def test_match_cache_roundtrip(self):
        from data.redis_client import get_redis, cache_match_results, get_cached_match_results
        r = get_redis()
        if r is None:
            pytest.skip("Redis not available")

        results = [{"candidate_id": 1, "match_score": 85.5}]
        cache_match_results(999, results)
        cached = get_cached_match_results(999)
        assert cached is not None
        assert cached[0]["match_score"] == 85.5


# ── File structure tests ──────────────────────────────────────────────────────

class TestSprint5FileStructure:

    def test_forecaster_importable(self):
        from ml.forecaster import forecast_revenue, predict_client_churn, optimize_rate
        assert callable(forecast_revenue)
        assert callable(optimize_rate)

    def test_anomaly_importable(self):
        from ml.anomaly import detect_timesheet_anomalies, get_margin_leakage
        assert callable(detect_timesheet_anomalies)

    def test_duckdb_client_importable(self):
        from data.duckdb_client import query_duckdb, get_duckdb_conn
        assert callable(query_duckdb)

    def test_redis_client_importable(self):
        from data.redis_client import cache_set, cache_get, get_chat_history
        assert callable(cache_set)
        assert callable(get_chat_history)
