"""
ml/predictor.py
ML prediction models for Sprint 4:
  #2 Submission success — interview / shortlist / hire probability
  #3 Attrition risk     — quit / terminate / disengage prediction

Both use XGBoost classifiers trained on seed data.
Models are saved to data/models/ and loaded on first use.
MLflow tracks all experiments and model metrics.

Usage:
    from ml.predictor import predict_submission_success, predict_attrition_risk

    probs = predict_submission_success(candidate_id=5, job_id=3, recruiter_id=1)
    # {"interview": 0.72, "shortlist": 0.45, "hire": 0.23}

    risk = predict_attrition_risk(candidate_id=5)
    # {"risk_score": 0.68, "risk_level": "high", "signals": [...]}
"""
import logging
import os
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from data.logger import get_logger, log_prediction_event
from ml.performance import timed

logger = get_logger("ml.predictor")

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

SUBMISSION_MODEL_PATH = MODEL_DIR / "submission_success.pkl"
ATTRITION_MODEL_PATH  = MODEL_DIR / "attrition_risk.pkl"


# ── Feature engineering ───────────────────────────────────────────────────────

def build_submission_features(candidate, job, recruiter_id: Optional[int] = None) -> pd.DataFrame:
    """
    Build feature vector for submission success prediction.
    Features mirror what a recruiter knows at submission time.
    """
    from ml.matcher import (
        score_semantic, score_skill_overlap, score_visa,
        score_yoe, score_rate, score_location,
    )

    skill_score, skill_gap = score_skill_overlap(
        candidate.skills or [], job.required_skills or []
    )

    features = {
        "match_score":      score_semantic(candidate.embedding, job.embedding),
        "skill_overlap":    skill_score,
        "visa_compatible":  score_visa(candidate.visa_status, job.visa_requirement),
        "yoe_score":        score_yoe(candidate.yoe or 0, job.min_yoe or 0, job.max_yoe),
        "rate_score":       score_rate(candidate.rate, job.rate_min, job.rate_max),
        "location_score":   score_location(candidate.location, job.location, job.remote_ok or False),
        "n_skills":         len(candidate.skills or []),
        "n_required":       len(job.required_skills or []),
        "n_missing":        len(skill_gap.get("missing", [])),
        "candidate_yoe":    candidate.yoe or 0,
        "job_min_yoe":      job.min_yoe or 0,
        "rate_delta":       (candidate.rate or 0) - (job.rate_min or 0),
        "recruiter_id":     recruiter_id or 0,
    }
    return pd.DataFrame([features])


def build_attrition_features(candidate) -> pd.DataFrame:
    """
    Build feature vector for attrition risk prediction.
    Uses signals available from timesheet + payroll + placement data.
    """
    features = {
        "tenure_days":            candidate.tenure_days or 0,
        "comms_gap_days":         candidate.comms_gap_days or 0,
        "overtime_pct":           candidate.overtime_pct or 0.0,
        "client_feedback_score":  candidate.client_feedback_score or 3.0,
        "yoe":                    candidate.yoe or 0,
        "is_active":              1 if candidate.is_active_contractor else 0,
    }
    return pd.DataFrame([features])


# ── Synthetic training data ───────────────────────────────────────────────────

def generate_submission_training_data(n: int = 500) -> tuple[pd.DataFrame, pd.Series]:
    """
    Generate synthetic training data for submission success model.
    Based on domain knowledge about what drives placement success.
    """
    import random
    random.seed(42)
    np.random.seed(42)

    rows = []
    labels = []

    for _ in range(n):
        match_score     = np.random.beta(5, 3)
        skill_overlap   = np.random.beta(4, 2)
        visa_compatible = np.random.choice([0, 1], p=[0.2, 0.8])
        yoe_score       = np.random.beta(3, 2)
        rate_score      = np.random.beta(4, 3)
        location_score  = np.random.choice([0.3, 0.7, 1.0], p=[0.2, 0.3, 0.5])
        n_skills        = random.randint(2, 12)
        n_required      = random.randint(3, 8)
        n_missing       = max(0, random.randint(0, n_required - 1))
        candidate_yoe   = random.uniform(1, 15)
        job_min_yoe     = random.uniform(1, 8)
        rate_delta      = random.uniform(-20, 30)
        recruiter_id    = random.randint(1, 5)

        # Label: hire probability driven by match quality
        hire_prob = (
            0.3 * match_score +
            0.25 * skill_overlap +
            0.15 * visa_compatible +
            0.1  * yoe_score +
            0.1  * rate_score +
            0.1  * location_score
        )
        # Add noise
        hire_prob = np.clip(hire_prob + np.random.normal(0, 0.05), 0, 1)
        label = 1 if hire_prob > 0.5 else 0

        rows.append({
            "match_score": match_score, "skill_overlap": skill_overlap,
            "visa_compatible": visa_compatible, "yoe_score": yoe_score,
            "rate_score": rate_score, "location_score": location_score,
            "n_skills": n_skills, "n_required": n_required,
            "n_missing": n_missing, "candidate_yoe": candidate_yoe,
            "job_min_yoe": job_min_yoe, "rate_delta": rate_delta,
            "recruiter_id": recruiter_id,
        })
        labels.append(label)

    return pd.DataFrame(rows), pd.Series(labels)


def generate_attrition_training_data(n: int = 300) -> tuple[pd.DataFrame, pd.Series]:
    """Generate synthetic attrition training data."""
    np.random.seed(42)

    rows = []
    labels = []

    for _ in range(n):
        tenure_days           = np.random.exponential(200)
        comms_gap_days        = np.random.exponential(5)
        overtime_pct          = np.random.beta(2, 5) * 30
        client_feedback_score = np.random.beta(4, 2) * 5
        yoe                   = np.random.uniform(1, 15)
        is_active             = 1

        # Attrition driven by comms gaps and low feedback
        risk = (
            0.3 * min(comms_gap_days / 30, 1) +
            0.25 * max(0, (3 - client_feedback_score) / 3) +
            0.2  * min(overtime_pct / 25, 1) +
            0.15 * max(0, 1 - tenure_days / 365) +
            0.1  * (1 - min(yoe / 10, 1))
        )
        risk = np.clip(risk + np.random.normal(0, 0.05), 0, 1)
        label = 1 if risk > 0.4 else 0

        rows.append({
            "tenure_days": tenure_days, "comms_gap_days": comms_gap_days,
            "overtime_pct": overtime_pct, "client_feedback_score": client_feedback_score,
            "yoe": yoe, "is_active": is_active,
        })
        labels.append(label)

    return pd.DataFrame(rows), pd.Series(labels)


# ── Model training ────────────────────────────────────────────────────────────

def train_submission_model(log_to_mlflow: bool = True) -> object:
    """Train and save the submission success model."""
    from xgboost import XGBClassifier
    from sklearn.model_selection import cross_val_score

    logger.info("Training submission success model...")
    X, y = generate_submission_training_data(n=500)

    model = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        use_label_encoder=False, eval_metric="logloss",
        random_state=42,
    )
    model.fit(X, y)

    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")
    logger.info(f"Submission model AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    if log_to_mlflow:
        try:
            import mlflow
            mlflow.set_experiment("submission_success")
            with mlflow.start_run():
                mlflow.log_metric("cv_auc_mean", cv_scores.mean())
                mlflow.log_metric("cv_auc_std", cv_scores.std())
                mlflow.xgboost.log_model(model, "model")
        except Exception as e:
            logger.warning(f"MLflow logging failed: {e}")

    with open(SUBMISSION_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info(f"Submission model saved to {SUBMISSION_MODEL_PATH}")
    return model


def train_attrition_model(log_to_mlflow: bool = True) -> object:
    """Train and save the attrition risk model."""
    from xgboost import XGBClassifier
    from sklearn.model_selection import cross_val_score

    logger.info("Training attrition risk model...")
    X, y = generate_attrition_training_data(n=300)

    model = XGBClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        use_label_encoder=False, eval_metric="logloss",
        random_state=42,
    )
    model.fit(X, y)

    cv_scores = cross_val_score(model, X, y, cv=5, scoring="roc_auc")
    logger.info(f"Attrition model AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    if log_to_mlflow:
        try:
            import mlflow
            mlflow.set_experiment("attrition_risk")
            with mlflow.start_run():
                mlflow.log_metric("cv_auc_mean", cv_scores.mean())
                mlflow.log_metric("cv_auc_std", cv_scores.std())
                mlflow.xgboost.log_model(model, "model")
        except Exception as e:
            logger.warning(f"MLflow logging failed: {e}")

    with open(ATTRITION_MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info(f"Attrition model saved to {ATTRITION_MODEL_PATH}")
    return model


# ── Model loading (lazy) ──────────────────────────────────────────────────────

_submission_model = None
_attrition_model  = None


def _get_submission_model():
    global _submission_model
    if _submission_model is None:
        if SUBMISSION_MODEL_PATH.exists():
            with open(SUBMISSION_MODEL_PATH, "rb") as f:
                _submission_model = pickle.load(f)
            logger.info("Loaded submission model from disk")
        else:
            logger.info("Submission model not found — training now...")
            _submission_model = train_submission_model()
    return _submission_model


def _get_attrition_model():
    global _attrition_model
    if _attrition_model is None:
        if ATTRITION_MODEL_PATH.exists():
            with open(ATTRITION_MODEL_PATH, "rb") as f:
                _attrition_model = pickle.load(f)
            logger.info("Loaded attrition model from disk")
        else:
            logger.info("Attrition model not found — training now...")
            _attrition_model = train_attrition_model()
    return _attrition_model


# ── Prediction API ────────────────────────────────────────────────────────────

@timed("predict_submission_success")
def predict_submission_success(
    candidate_id: int,
    job_id: int,
    recruiter_id: Optional[int] = None,
) -> dict:
    """
    Predict probability of candidate getting interview, shortlist, hire.

    Returns:
        {
          "interview": 0.72,
          "shortlist": 0.45,
          "hire": 0.23,
          "confidence": "high"
        }
    """
    import time
    from db.models import get_session, Candidate, Job

    start = time.perf_counter()
    session = get_session()
    try:
        candidate = session.get(Candidate, candidate_id)
        job = session.get(Job, job_id)
        if not candidate or not job:
            raise ValueError("Candidate or job not found")

        model = _get_submission_model()
        features = build_submission_features(candidate, job, recruiter_id)
        hire_prob = float(model.predict_proba(features)[0][1])

        # Derive interview and shortlist from hire probability
        interview_prob = min(1.0, hire_prob * 1.8)
        shortlist_prob = min(1.0, hire_prob * 1.3)

        confidence = "high" if hire_prob > 0.6 else "medium" if hire_prob > 0.35 else "low"

        result = {
            "interview":  round(interview_prob, 3),
            "shortlist":  round(shortlist_prob, 3),
            "hire":       round(hire_prob, 3),
            "confidence": confidence,
        }

        duration_ms = (time.perf_counter() - start) * 1000
        log_prediction_event("submission_success", "candidate", candidate_id,
                             hire_prob, duration_ms)

        # Persist prediction
        from db.queries import save_prediction
        save_prediction("candidate", candidate_id, "submission_success",
                        hire_prob, features.to_dict(orient="records")[0])

        return result

    finally:
        session.close()


@timed("predict_attrition_risk")
def predict_attrition_risk(candidate_id: int) -> dict:
    """
    Predict attrition risk for an active contractor.

    Returns:
        {
          "risk_score": 0.68,
          "risk_level": "high",
          "signals": ["High comms gap (12 days)", "Low client feedback (2.8/5)"]
        }
    """
    import time
    from db.models import get_session, Candidate

    start = time.perf_counter()
    session = get_session()
    try:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        model = _get_attrition_model()
        features = build_attrition_features(candidate)
        risk_score = float(model.predict_proba(features)[0][1])

        risk_level = "high" if risk_score > 0.6 else "medium" if risk_score > 0.35 else "low"

        # Human-readable signals
        signals = []
        if (candidate.comms_gap_days or 0) > 7:
            signals.append(f"High comms gap ({candidate.comms_gap_days} days)")
        if (candidate.client_feedback_score or 5) < 3.0:
            signals.append(f"Low client feedback ({candidate.client_feedback_score:.1f}/5)")
        if (candidate.overtime_pct or 0) > 20:
            signals.append(f"High overtime ({candidate.overtime_pct:.0f}%)")
        if (candidate.tenure_days or 365) < 90:
            signals.append("Short tenure (< 90 days)")

        result = {
            "risk_score": round(risk_score, 3),
            "risk_level": risk_level,
            "signals":    signals,
        }

        duration_ms = (time.perf_counter() - start) * 1000
        log_prediction_event("attrition_risk", "candidate", candidate_id,
                             risk_score, duration_ms)

        from db.queries import save_prediction
        save_prediction("candidate", candidate_id, "attrition_risk",
                        risk_score, features.to_dict(orient="records")[0])

        # Update candidate's attrition_risk_score
        from db.queries import update_candidate
        update_candidate(candidate_id, {"attrition_risk_score": risk_score})

        return result

    finally:
        session.close()


def retrain_all_models():
    """Retrain all models. Called from admin page or scheduler."""
    global _submission_model, _attrition_model
    logger.info("Retraining all prediction models...")
    _submission_model = train_submission_model()
    _attrition_model  = train_attrition_model()
    logger.info("All models retrained successfully")
