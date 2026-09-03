from __future__ import annotations

import json
import logging
import os
from typing import Any

import joblib
import pandas as pd

from app.ml.features import build_single_case_features

logger = logging.getLogger(__name__)

_MODEL_PATH = os.path.join("app", "ml", "model.pkl")
_FEATURE_COLS_PATH = os.path.join("app", "ml", "feature_columns.json")

# Prior base rates used as safety fallbacks
_BASE_RECOVERY_RATES: dict[str, float] = {
    "insufficient_funds": 0.60,
    "bank_timeout": 0.70,
    "expired_card": 0.12,
    "mandate_revoked": 0.05,
    "auth_required": 0.45,
    "generic_decline": 0.35,
}
_DEFAULT_BASE_RATE: float = 0.40

_loaded_model: Any | None = None
_loaded_feature_columns: list[str] | None = None


def _load_model_and_columns() -> tuple[Any, list[str]]:
    # Load and cache trained model and expected feature schema
    global _loaded_model, _loaded_feature_columns
    if _loaded_model is not None and _loaded_feature_columns is not None:
        return _loaded_model, _loaded_feature_columns

    if not os.path.exists(_MODEL_PATH) or not os.path.exists(_FEATURE_COLS_PATH):
        raise FileNotFoundError("Model artifacts missing from app/ml")

    _loaded_model = joblib.load(_MODEL_PATH)
    with open(_FEATURE_COLS_PATH, "r", encoding="utf-8") as f:
        _loaded_feature_columns = json.load(f)

    return _loaded_model, _loaded_feature_columns


def predict_recovery_probability(case_features: dict[str, Any]) -> float:
    # Predict recovery probability P in [0.0, 1.0] for a case
    decline_reason = case_features.get("decline_reason", "")

    if decline_reason not in _BASE_RECOVERY_RATES:
        return _DEFAULT_BASE_RATE

    try:
        model, feature_columns = _load_model_and_columns()
    except Exception:
        return _BASE_RECOVERY_RATES.get(decline_reason, _DEFAULT_BASE_RATE)

    try:
        X = build_single_case_features(case_features, feature_columns)
        X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
        proba = model.predict_proba(X)[0]
        return float(proba[1])
    except Exception as exc:
        logger.warning("Prediction fallback for %s: %s", decline_reason, exc)
        return _BASE_RECOVERY_RATES.get(decline_reason, _DEFAULT_BASE_RATE)