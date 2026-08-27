"""
Inference module for the payment recovery probability classifier.

Loads the trained model (app/ml/model.pkl) and feature column spec
(app/ml/feature_columns.json), and exposes a single function:

    predict_recovery_probability(case_features: dict) -> float

Returns the model's predicted probability of recovery (class 1) for a
single case. Handles missing/unexpected feature values gracefully by
falling back to the decline-reason base rate when the model cannot
produce a reliable prediction.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.ml.features import build_single_case_features

logger = logging.getLogger(__name__)

# Paths relative to project root
_MODEL_PATH = os.path.join("app", "ml", "model.pkl")
_FEATURE_COLS_PATH = os.path.join("app", "ml", "feature_columns.json")

# Fallback base rates when the model can't produce a reliable prediction.
# These match the industry priors from the synthetic data generator.
_BASE_RECOVERY_RATES: dict[str, float] = {
    "insufficient_funds": 0.60,
    "bank_timeout":       0.70,
    "expired_card":       0.12,
    "mandate_revoked":    0.05,
    "auth_required":      0.45,
    "generic_decline":    0.35,
}
_DEFAULT_BASE_RATE: float = 0.40  # fallback for completely unknown decline reasons

# Module-level cache so we don't reload from disk on every call
_loaded_model: Any | None = None
_loaded_feature_columns: list[str] | None = None


def _load_model_and_columns() -> tuple[Any, list[str]]:
    """Load the trained model and feature column list, with caching."""
    global _loaded_model, _loaded_feature_columns

    if _loaded_model is not None and _loaded_feature_columns is not None:
        return _loaded_model, _loaded_feature_columns

    if not os.path.exists(_MODEL_PATH):
        raise FileNotFoundError(
            f"Trained model not found at {_MODEL_PATH}. "
            f"Run 'python app/ml/train.py' first to train and save the model."
        )
    if not os.path.exists(_FEATURE_COLS_PATH):
        raise FileNotFoundError(
            f"Feature columns file not found at {_FEATURE_COLS_PATH}. "
            f"Run 'python app/ml/train.py' first."
        )

    _loaded_model = joblib.load(_MODEL_PATH)
    with open(_FEATURE_COLS_PATH, "r", encoding="utf-8") as f:
        _loaded_feature_columns = json.load(f)

    logger.info(
        "Loaded model from %s (%d features)",
        _MODEL_PATH, len(_loaded_feature_columns),
    )
    return _loaded_model, _loaded_feature_columns


def predict_recovery_probability(case_features: dict[str, Any]) -> float:
    """Predict the probability of recovering a failed payment.

    Parameters
    ----------
    case_features : dict
        A single case record with raw column names (decline_reason, payment_method,
        amount, retry_attempt_number, etc.). Does not need to include case_id or
        the recovered label.

    Returns
    -------
    float
        Predicted probability of recovery, in [0.0, 1.0].
        Falls back to the decline-reason base rate if the model cannot be loaded
        or if the input contains an unrecognized decline_reason.
    """
    decline_reason = case_features.get("decline_reason", "")

    # --- Validate decline_reason ---
    known_reasons = set(_BASE_RECOVERY_RATES.keys())
    if decline_reason not in known_reasons:
        logger.warning(
            "Unknown decline_reason '%s' — falling back to default base rate %.2f. "
            "Known reasons: %s",
            decline_reason, _DEFAULT_BASE_RATE, sorted(known_reasons),
        )
        return _DEFAULT_BASE_RATE

    # --- Load model ---
    try:
        model, feature_columns = _load_model_and_columns()
    except FileNotFoundError as exc:
        logger.warning(
            "Model not available (%s) — falling back to base rate for '%s'",
            exc, decline_reason,
        )
        return _BASE_RECOVERY_RATES.get(decline_reason, _DEFAULT_BASE_RATE)

    # --- Build feature vector ---
    try:
        X = build_single_case_features(case_features, feature_columns)
        # Ensure correct dtypes (all numeric)
        X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    except Exception:
        logger.exception(
            "Feature construction failed for case — falling back to base rate for '%s'",
            decline_reason,
        )
        return _BASE_RECOVERY_RATES.get(decline_reason, _DEFAULT_BASE_RATE)

    # --- Predict ---
    try:
        proba = model.predict_proba(X)[0]
        # predict_proba returns [P(class=0), P(class=1)]
        recovery_prob = float(proba[1])
    except Exception:
        logger.exception(
            "Model prediction failed — falling back to base rate for '%s'",
            decline_reason,
        )
        return _BASE_RECOVERY_RATES.get(decline_reason, _DEFAULT_BASE_RATE)

    return recovery_prob
