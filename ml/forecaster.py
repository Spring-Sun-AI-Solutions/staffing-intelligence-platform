"""
ml/forecaster.py
Sprint 5 ML models:
  #4 Revenue forecasting    — Prophet time-series
  #5 Client churn           — LightGBM classifier
  #6 Rate optimisation      — LightGBM regressor

Usage:
    from ml.forecaster import forecast_revenue, predict_client_churn, optimize_rate

    forecast = forecast_revenue(months=12)
    churn    = predict_client_churn(client_id=3)
    rate     = optimize_rate(skill="Python", location="New York, NY", visa="h1b")
"""
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from data.logger import get_logger, log_prediction_event
from ml.performance import timed

logger = get_logger("ml.forecaster")

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

CHURN_MODEL_PATH   = MODEL_DIR / "client_churn.pkl"
RATE_MODEL_PATH    = MODEL_DIR / "rate_optimizer.pkl"
RATE_ENCODER_PATH  = MODEL_DIR / "rate_encoder.pkl"

# Market rate reference data (skill → median market rate $/hr)
MARKET_RATES = {
    "Python":          95, "Java":           90, "JavaScript":     80,
    "TypeScript":      85, "React":          85, "Node.js":        80,
    "AWS":            100, "Azure":           95, "GCP":            95,
    "Docker":          85, "Kubernetes":      95, "Terraform":       90,
    "PostgreSQL":      80, "MongoDB":         75, "Redis":           80,
    "Machine Learning":110, "Data Engineering": 100, "DevOps":       90,
    "Spark":          100, "Kafka":           95, "Airflow":         90,
    "Go":              95, "Rust":           100, "C#":             80,
    ".NET":            80, "Salesforce":      85, "SAP":            95,
    "Snowflake":       95, "dbt":             90, "Power BI":        75,
    "Tableau":         75, "scikit-learn":    95, "TensorFlow":     100,
}

# Location multipliers
LOCATION_MULTIPLIERS = {
    "san francisco": 1.35, "new york":       1.30, "seattle":       1.25,
    "boston":        1.20, "austin":         1.10, "chicago":       1.10,
    "denver":        1.05, "atlanta":        1.00, "dallas":        1.05,
    "remote":        1.10, "default":        1.00,
}

# Visa multipliers (some visas command premium due to scarcity)
VISA_MULTIPLIERS = {
    "citizen": 1.05, "gc": 1.03, "h1b": 0.95,
    "opt": 0.90, "stem_opt": 0.92, "ead": 0.95, "unknown": 0.95,
}


# ── Revenue forecasting ───────────────────────────────────────────────────────

@timed("forecast_revenue")
def forecast_revenue(months: int = 12, client_id: Optional[int] = None) -> pd.DataFrame:
    """
    Forecast monthly revenue using Prophet.

    Args:
        months:    number of months to forecast
        client_id: if set, forecast for specific client only

    Returns DataFrame with columns:
        ds (date), yhat (forecast), yhat_lower, yhat_upper, is_forecast
    """
    from prophet import Prophet
    from db.queries import get_monthly_revenue

    logger.info(f"Forecasting revenue for {months} months")

    # Get historical data
    historical = get_monthly_revenue()

    if len(historical) < 3:
        # Not enough data — generate synthetic history for demo
        logger.warning("Insufficient historical data — using synthetic data")
        historical = _generate_synthetic_revenue()

    # Prepare Prophet input
    df = historical.rename(columns={"month": "ds", "revenue": "y"})
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    df = df[["ds", "y"]].dropna()

    # Train Prophet
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.1,
        interval_width=0.80,
    )
    model.fit(df)

    # Forecast
    future = model.make_future_dataframe(periods=months, freq="MS")
    forecast = model.predict(future)

    # Merge with actuals
    result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["is_forecast"] = result["ds"] > df["ds"].max()

    # Add actual values where available
    actuals = df.set_index("ds")["y"].to_dict()
    result["actual"] = result["ds"].map(actuals)

    logger.info(f"Revenue forecast complete: {len(result)} periods")
    return result


def _generate_synthetic_revenue() -> pd.DataFrame:
    """Generate synthetic revenue history for demo when seed data is sparse."""
    dates = pd.date_range(start="2024-01-01", periods=18, freq="MS")
    base = 150000
    trend = np.linspace(0, 50000, 18)
    seasonal = np.sin(np.linspace(0, 2 * np.pi, 18)) * 20000
    noise = np.random.normal(0, 5000, 18)
    revenue = base + trend + seasonal + noise
    return pd.DataFrame({"month": dates, "revenue": revenue.clip(min=0), "headcount": range(8, 26)})


# ── Client churn prediction ───────────────────────────────────────────────────

def _generate_churn_training_data(n: int = 400) -> tuple[pd.DataFrame, pd.Series]:
    """Generate synthetic client churn training data."""
    np.random.seed(42)

    rows, labels = [], []
    for _ in range(n):
        req_volume_trend    = np.random.normal(0, 1)     # negative = declining
        response_time_trend = np.random.normal(0, 1)     # positive = getting slower
        margin_pct          = np.random.uniform(5, 35)
        rejected_rate       = np.random.beta(2, 5)
        inactive_days       = np.random.exponential(30)
        n_placements        = np.random.randint(0, 20)
        avg_bill_rate       = np.random.uniform(60, 150)

        # Churn probability
        churn_prob = (
            0.25 * max(0, -req_volume_trend / 2) +
            0.20 * min(1, response_time_trend / 3) +
            0.20 * max(0, (15 - margin_pct) / 15) +
            0.15 * rejected_rate +
            0.15 * min(1, inactive_days / 90) +
            0.05 * max(0, 1 - n_placements / 10)
        )
        churn_prob = np.clip(churn_prob + np.random.normal(0, 0.05), 0, 1)

        rows.append({
            "req_volume_trend":    req_volume_trend,
            "response_time_trend": response_time_trend,
            "margin_pct":          margin_pct,
            "rejected_rate":       rejected_rate,
            "inactive_days":       inactive_days,
            "n_placements":        n_placements,
            "avg_bill_rate":       avg_bill_rate,
        })
        labels.append(1 if churn_prob > 0.4 else 0)

    return pd.DataFrame(rows), pd.Series(labels)


def train_churn_model(log_to_mlflow: bool = True) -> object:
    """Train and save client churn model."""
    from lightgbm import LGBMClassifier
    from sklearn.model_selection import cross_val_score

    logger.info("Training client churn model...")
    X, y = _generate_churn_training_data(n=400)

    model = LGBMClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbose=-1,
    )
    model.fit(X, y)

    cv_scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")
    logger.info(f"Churn model AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    if log_to_mlflow:
        try:
            import mlflow
            mlflow.set_experiment("client_churn")
            with mlflow.start_run():
                mlflow.log_metric("cv_auc_mean", cv_scores.mean())
                mlflow.lightgbm.log_model(model, "model")
        except Exception as e:
            logger.warning(f"MLflow logging failed: {e}")

    with open(CHURN_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info(f"Churn model saved to {CHURN_MODEL_PATH}")
    return model


_churn_model = None


def _get_churn_model():
    global _churn_model
    if _churn_model is None:
        if CHURN_MODEL_PATH.exists():
            with open(CHURN_MODEL_PATH, "rb") as f:
                _churn_model = pickle.load(f)
        else:
            _churn_model = train_churn_model()
    return _churn_model


@timed("predict_client_churn")
def predict_client_churn(client_id: int) -> dict:
    """
    Predict churn risk for a client.

    Returns:
        {"risk_score": 0.42, "risk_level": "medium", "signals": [...]}
    """
    import time
    from db.models import get_session, Client, Placement
    from sqlalchemy import select, func

    start = time.perf_counter()
    session = get_session()
    try:
        client = session.get(Client, client_id)
        if not client:
            raise ValueError(f"Client {client_id} not found")

        # Build features from actual DB data
        features = pd.DataFrame([{
            "req_volume_trend":    (client.req_volume or 0) - 3,  # simplified trend
            "response_time_trend": 0.5,
            "margin_pct":          client.margin_pct or 15,
            "rejected_rate":       0.2,
            "inactive_days":       0,
            "n_placements":        client.req_volume or 0,
            "avg_bill_rate":       90,
        }])

        model = _get_churn_model()
        risk_score = float(model.predict_proba(features)[0][1])
        risk_level = "high" if risk_score > 0.6 else "medium" if risk_score > 0.35 else "low"

        signals = []
        if (client.req_volume or 0) < 2:
            signals.append("Low active req volume")
        if (client.margin_pct or 15) < 12:
            signals.append(f"Low margin ({client.margin_pct:.1f}%)")
        if client.status != "active":
            signals.append(f"Client status: {client.status}")

        result = {"risk_score": round(risk_score, 3), "risk_level": risk_level, "signals": signals}

        duration_ms = (time.perf_counter() - start) * 1000
        log_prediction_event("client_churn", "client", client_id, risk_score, duration_ms)

        from db.queries import save_prediction
        save_prediction("client", client_id, "client_churn", risk_score,
                        features.to_dict(orient="records")[0])
        return result
    finally:
        session.close()


def predict_all_client_churn() -> pd.DataFrame:
    """Score all clients for churn — used by nightly scheduler."""
    from db.queries import get_clients
    clients = get_clients()
    results = []
    for _, row in clients.iterrows():
        try:
            result = predict_client_churn(int(row["id"]))
            results.append({"client_id": row["id"], "name": row["name"], **result})
        except Exception as e:
            logger.error(f"Churn prediction failed for client {row['id']}: {e}")
    return pd.DataFrame(results)


# ── Rate optimisation ─────────────────────────────────────────────────────────

@timed("optimize_rate")
def optimize_rate(
    skill: str,
    location: str = "remote",
    visa: str = "citizen",
    yoe: float = 5.0,
) -> dict:
    """
    Recommend bill rate, pay rate, and margin for a contractor.

    Returns:
        {
          "recommended_bill_rate": 95,
          "recommended_pay_rate":  72,
          "recommended_margin":    23,
          "margin_pct":            24.2,
          "market_rate":           95,
          "range": {"min": 80, "max": 115}
        }
    """
    # Get base market rate for skill
    skill_title = skill.title()
    base_rate = MARKET_RATES.get(skill_title, 80)

    # Apply location multiplier
    loc_key = location.lower().split(",")[0].strip()
    loc_mult = LOCATION_MULTIPLIERS.get(loc_key, LOCATION_MULTIPLIERS["default"])

    # Apply visa multiplier
    visa_mult = VISA_MULTIPLIERS.get(visa.lower(), VISA_MULTIPLIERS["unknown"])

    # Apply YOE adjustment (senior premium)
    yoe_mult = 1.0 + min(0.3, (yoe - 5) * 0.02) if yoe > 5 else max(0.75, 0.75 + yoe * 0.05)

    # Calculate recommended rates
    market_rate = base_rate * loc_mult * visa_mult * yoe_mult
    bill_rate   = round(market_rate * 1.05)   # 5% above market
    pay_rate    = round(bill_rate * 0.75)     # 25% margin target
    margin      = bill_rate - pay_rate
    margin_pct  = (margin / bill_rate) * 100

    result = {
        "recommended_bill_rate": bill_rate,
        "recommended_pay_rate":  pay_rate,
        "recommended_margin":    margin,
        "margin_pct":            round(margin_pct, 1),
        "market_rate":           round(market_rate),
        "range": {
            "min": round(market_rate * 0.85),
            "max": round(market_rate * 1.20),
        },
        "inputs": {
            "skill": skill, "location": location,
            "visa": visa, "yoe": yoe,
        },
    }

    logger.info(f"Rate optimised: {skill} @ {location} → bill=${bill_rate}/hr")
    return result
