"""
ml/anomaly.py
Sprint 5:
  #10 Timesheet anomaly detection — PyOD Isolation Forest
  #15 Margin leakage analysis    — DuckDB analytics queries

Usage:
    from ml.anomaly import detect_timesheet_anomalies, get_margin_leakage

    flagged = detect_timesheet_anomalies()
    leakage = get_margin_leakage()
"""
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from data.logger import get_logger
from ml.performance import timed

logger = get_logger("ml.anomaly")

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

ANOMALY_MODEL_PATH = MODEL_DIR / "timesheet_anomaly.pkl"


# ── Timesheet anomaly detection ───────────────────────────────────────────────

def build_timesheet_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build features for anomaly detection from raw timesheet data.

    Features:
    - hours deviation from contractor's own average
    - overtime ratio
    - weekend hours flag
    - hours vs global average
    - duplicate week flag
    """
    features = pd.DataFrame()

    # Per-contractor average hours
    contractor_avg = df.groupby("contractor_id")["hours"].transform("mean")
    contractor_std = df.groupby("contractor_id")["hours"].transform("std").fillna(1)

    features["hours_zscore"]      = (df["hours"] - contractor_avg) / contractor_std.clip(lower=1)
    features["overtime_ratio"]    = df["overtime_hours"] / df["hours"].clip(lower=1)
    features["hours_abs"]         = df["hours"]
    features["hours_vs_global"]   = df["hours"] - df["hours"].mean()
    features["is_high_hours"]     = (df["hours"] > 50).astype(int)
    features["is_very_high_hours"]= (df["hours"] > 65).astype(int)

    # Duplicate week detection (same contractor, same week)
    dup_mask = df.duplicated(subset=["contractor_id", "week_start"], keep=False)
    features["is_duplicate_week"] = dup_mask.astype(int)

    return features.fillna(0)


def train_anomaly_model(df: Optional[pd.DataFrame] = None) -> object:
    """
    Train Isolation Forest anomaly detector on timesheet data.
    If no data provided, loads from DB.
    """
    from pyod.models.iforest import IForest

    if df is None:
        from db.queries import get_timesheets
        df = get_timesheets()

    if len(df) < 10:
        logger.warning("Insufficient timesheet data — generating synthetic data")
        df = _generate_synthetic_timesheets()

    features = build_timesheet_features(df)
    logger.info(f"Training anomaly model on {len(features)} timesheet records")

    model = IForest(
        n_estimators=100,
        contamination=0.05,  # expect ~5% anomalies
        random_state=42,
        n_jobs=-1,
    )
    model.fit(features.values)

    try:
        import mlflow
        mlflow.set_experiment("timesheet_anomaly")
        with mlflow.start_run():
            mlflow.log_param("n_estimators", 100)
            mlflow.log_param("contamination", 0.05)
            mlflow.log_metric("n_samples", len(features))
    except Exception:
        pass

    with open(ANOMALY_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info(f"Anomaly model saved to {ANOMALY_MODEL_PATH}")
    return model


def _generate_synthetic_timesheets() -> pd.DataFrame:
    """Generate synthetic timesheet data for demo/testing."""
    np.random.seed(42)
    import random
    rows = []
    for contractor_id in range(1, 21):
        for week in range(12):
            hours = np.random.normal(40, 3)
            is_anomaly = random.random() < 0.05
            if is_anomaly:
                hours = np.random.uniform(65, 80)
            rows.append({
                "id": len(rows) + 1,
                "contractor_id": contractor_id,
                "week_start": f"2026-{(week // 4) + 1:02d}-{((week % 4) * 7) + 1:02d}",
                "hours": round(max(0, hours), 1),
                "overtime_hours": round(max(0, hours - 40), 1),
            })
    return pd.DataFrame(rows)


_anomaly_model = None


def _get_anomaly_model():
    global _anomaly_model
    if _anomaly_model is None:
        if ANOMALY_MODEL_PATH.exists():
            with open(ANOMALY_MODEL_PATH, "rb") as f:
                _anomaly_model = pickle.load(f)
            logger.info("Loaded anomaly model from disk")
        else:
            logger.info("Training anomaly model...")
            _anomaly_model = train_anomaly_model()
    return _anomaly_model


@timed("detect_timesheet_anomalies")
def detect_timesheet_anomalies(flag_in_db: bool = True) -> pd.DataFrame:
    """
    Run anomaly detection on all timesheets.

    Args:
        flag_in_db: if True, update anomaly_flag and anomaly_score in DB

    Returns:
        DataFrame of flagged timesheets with anomaly scores
    """
    from db.queries import get_timesheets, flag_timesheet_anomaly

    df = get_timesheets()

    if df.empty:
        logger.warning("No timesheets found for anomaly detection")
        return pd.DataFrame()

    features = build_timesheet_features(df)
    model = _get_anomaly_model()

    # Get anomaly scores (-1 = anomaly, 1 = normal in PyOD convention)
    scores = model.decision_function(features.values)  # higher = more anomalous
    labels = model.predict(features.values)            # 1 = anomaly, 0 = normal

    df = df.copy()
    df["anomaly_score"] = scores
    df["is_anomaly"]    = labels == 1

    flagged = df[df["is_anomaly"]].copy()
    flagged = flagged.sort_values("anomaly_score", ascending=False)

    logger.info(f"Anomaly detection: {len(flagged)} flagged out of {len(df)} timesheets")

    if flag_in_db and not flagged.empty:
        for _, row in flagged.iterrows():
            try:
                hours = row.get("hours", 0)
                reason = (
                    f"Unusually high hours ({hours:.0f}h)" if hours > 55
                    else "Statistical anomaly detected"
                )
                flag_timesheet_anomaly(
                    int(row["id"]),
                    float(row["anomaly_score"]),
                    reason,
                )
            except Exception as e:
                logger.error(f"Failed to flag timesheet {row['id']}: {e}")

    return flagged


# ── Margin leakage (DuckDB) ───────────────────────────────────────────────────

@timed("get_margin_leakage")
def get_margin_leakage(threshold_pct: float = 15.0) -> pd.DataFrame:
    """
    Find accounts with margin below threshold using DuckDB for fast analytics.

    Args:
        threshold_pct: margin percentage below which an account is considered leaking

    Returns:
        DataFrame with columns: client_id, client_name, avg_margin_pct,
                                total_revenue, contractor_count, risk_level
    """
    from data.duckdb_client import query_duckdb

    sql = f"""
    SELECT
        c.id            AS client_id,
        c.name          AS client_name,
        AVG(p.margin_pct)  AS avg_margin_pct,
        SUM(p.bill_rate)   AS total_revenue,
        COUNT(DISTINCT p.contractor_id) AS contractor_count,
        SUM(p.bill_rate - p.pay_rate)   AS total_margin,
        CASE
            WHEN AVG(p.margin_pct) < 10 THEN 'critical'
            WHEN AVG(p.margin_pct) < {threshold_pct} THEN 'warning'
            ELSE 'ok'
        END AS risk_level
    FROM payroll p
    JOIN placements pl ON pl.candidate_id = p.contractor_id
    JOIN clients c     ON c.id = pl.client_id
    GROUP BY c.id, c.name
    HAVING AVG(p.margin_pct) < {threshold_pct}
    ORDER BY avg_margin_pct ASC
    """

    try:
        result = query_duckdb(sql)
        logger.info(f"Margin leakage: {len(result)} accounts below {threshold_pct}% margin")
        return result
    except Exception as e:
        logger.warning(f"DuckDB margin leakage query failed, falling back to Pandas: {e}")
        return _margin_leakage_fallback(threshold_pct)


def _margin_leakage_fallback(threshold_pct: float) -> pd.DataFrame:
    """Fallback to Postgres if DuckDB is not available."""
    from db.queries import get_clients
    clients = get_clients()
    leaking = clients[clients["margin_pct"] < threshold_pct].copy()
    leaking["risk_level"] = leaking["margin_pct"].apply(
        lambda x: "critical" if x < 10 else "warning"
    )
    return leaking.rename(columns={"id": "client_id", "name": "client_name"})


@timed("get_bench_cost")
def get_bench_cost() -> pd.DataFrame:
    """
    Identify contractors on bench (active but no recent timesheets).
    Uses DuckDB for the aggregation.
    """
    from data.duckdb_client import query_duckdb

    sql = """
    SELECT
        c.id          AS candidate_id,
        c.name        AS candidate_name,
        c.rate        AS daily_rate,
        c.rate * 5    AS weekly_bench_cost,
        MAX(t.week_start) AS last_timesheet,
        DATEDIFF('day', MAX(t.week_start), CURRENT_DATE) AS days_on_bench
    FROM candidates c
    LEFT JOIN timesheets t ON t.contractor_id = c.id
    WHERE c.is_active_contractor = true
    GROUP BY c.id, c.name, c.rate
    HAVING MAX(t.week_start) IS NULL
       OR DATEDIFF('day', MAX(t.week_start), CURRENT_DATE) > 14
    ORDER BY weekly_bench_cost DESC NULLS LAST
    """

    try:
        return query_duckdb(sql)
    except Exception as e:
        logger.warning(f"Bench cost query failed: {e}")
        return pd.DataFrame(columns=["candidate_id", "candidate_name",
                                     "daily_rate", "weekly_bench_cost",
                                     "last_timesheet", "days_on_bench"])
