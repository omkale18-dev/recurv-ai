"""
Feature engineering for the payment recovery probability classifier.

Input columns (from training_data.csv / demo_batch.csv):
---------------------------------------------------------
  case_id                           : str   — unique identifier (DROPPED, not a feature)
  decline_reason                    : str   — one-hot encoded into 6 binary columns
  payment_method                    : str   — one-hot encoded into 3 binary columns
  amount                            : float — kept as-is (log-normal ₹100–₹15000)
  retry_attempt_number              : int   — kept as-is (1–4, NPCI cap)
  previous_retries_on_this_case     : int   — kept as-is (= retry_attempt_number - 1)
  days_since_last_failure           : int   — kept as-is (0–10)
  day_of_month                      : int   — kept as-is (1–31)
  hour_of_day                       : int   — kept as-is (0–23)
  is_salary_window                  : bool  — converted to int (0/1)
  customer_historical_success_rate  : float — kept as-is (0.0–1.0)
  customer_tenure_days              : int   — kept as-is (1–1500)
  is_subscription                   : bool  — converted to int (0/1)

Target column:
--------------
  recovered                         : bool  — binary label (True/False → 1/0)

One-hot encoding strategy:
--------------------------
  decline_reason → decline_reason_insufficient_funds, decline_reason_expired_card,
                   decline_reason_bank_timeout, decline_reason_mandate_revoked,
                   decline_reason_auth_required, decline_reason_generic_decline
  payment_method → payment_method_upi, payment_method_card, payment_method_netbanking

All one-hot columns use drop=None (no reference category dropped) to preserve full
interpretability for per-category analysis and to avoid information loss in tree-based
models. For logistic regression this introduces collinearity, but with regularization
(default L2) this is acceptable and preferred over losing a category.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical categorical values — used for one-hot encoding consistency between
# training and inference. If an unseen value appears at inference time, all
# one-hot columns for that category will be 0 (handled gracefully).
DECLINE_REASON_VALUES: list[str] = [
    "auth_required",
    "bank_timeout",
    "expired_card",
    "generic_decline",
    "insufficient_funds",
    "mandate_revoked",
]

PAYMENT_METHOD_VALUES: list[str] = [
    "card",
    "netbanking",
    "upi",
]

# Columns that are boolean in the raw CSV and need int conversion
BOOL_COLUMNS: list[str] = ["is_salary_window", "is_subscription"]

# Columns kept as-is (numeric)
NUMERIC_COLUMNS: list[str] = [
    "amount",
    "retry_attempt_number",
    "previous_retries_on_this_case",
    "days_since_last_failure",
    "day_of_month",
    "hour_of_day",
    "customer_historical_success_rate",
    "customer_tenure_days",
]

TARGET_COLUMN: str = "recovered"


def _coerce_bool(series: pd.Series) -> pd.Series:
    """Convert a column that may be bool, str('True'/'False'), or int to int 0/1."""
    if series.dtype == bool:
        return series.astype(int)
    if series.dtype == object:
        return series.map({"True": 1, "False": 0, "true": 1, "false": 0}).fillna(0).astype(int)
    return series.astype(int)


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Transform raw case data into model-ready feature matrix.

    Parameters
    ----------
    df : pd.DataFrame
        Raw dataframe with columns as documented in the module docstring.
        Must contain all input columns. Target column (recovered) is optional.

    Returns
    -------
    features_df : pd.DataFrame
        Feature matrix with one-hot encoded categoricals and numeric columns.
        If 'recovered' was present in the input, it is included as the last column.
    feature_columns : list[str]
        Ordered list of feature column names (excludes the target column).
    """
    result = pd.DataFrame(index=df.index)

    # --- One-hot encode decline_reason ---
    for val in DECLINE_REASON_VALUES:
        col_name = f"decline_reason_{val}"
        if "decline_reason" in df.columns:
            result[col_name] = (df["decline_reason"] == val).astype(int)
        else:
            result[col_name] = 0

    # --- One-hot encode payment_method ---
    for val in PAYMENT_METHOD_VALUES:
        col_name = f"payment_method_{val}"
        if "payment_method" in df.columns:
            result[col_name] = (df["payment_method"] == val).astype(int)
        else:
            result[col_name] = 0

    # --- Boolean columns → int ---
    for col in BOOL_COLUMNS:
        if col in df.columns:
            result[col] = _coerce_bool(df[col])
        else:
            result[col] = 0

    # --- Numeric columns (keep as-is) ---
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            result[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            result[col] = 0

    # --- Build feature column list (everything except target) ---
    feature_columns = list(result.columns)

    # --- Append target if present ---
    if TARGET_COLUMN in df.columns:
        result[TARGET_COLUMN] = _coerce_bool(df[TARGET_COLUMN])

    return result, feature_columns


def build_single_case_features(
    case: dict[str, Any], feature_columns: list[str]
) -> pd.DataFrame:
    """Build a feature vector for a single case dict, aligned to saved feature columns.

    Parameters
    ----------
    case : dict
        A single case record with raw column names and values.
    feature_columns : list[str]
        The exact ordered list of feature column names saved during training.

    Returns
    -------
    pd.DataFrame
        A single-row DataFrame with columns matching feature_columns.
    """
    df = pd.DataFrame([case])
    features_df, _ = build_features(df)

    # Align to the exact training-time column order, filling missing with 0
    aligned = pd.DataFrame(columns=feature_columns)
    for col in feature_columns:
        if col in features_df.columns:
            aligned[col] = features_df[col].values
        else:
            logger.warning("Feature column '%s' not found in case data; defaulting to 0", col)
            aligned[col] = [0]

    return aligned
