from __future__ import annotations

import logging
from typing import Any
import pandas as pd

logger = logging.getLogger(__name__)

# Categorical domain sets for stable one-hot mapping
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

BOOL_COLUMNS: list[str] = ["is_salary_window", "is_subscription"]

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
    # Convert bool or string representations to int 0/1
    if series.dtype == bool:
        return series.astype(int)
    if series.dtype == object:
        return series.map({"True": 1, "False": 0, "true": 1, "false": 0}).fillna(0).astype(int)
    return series.astype(int)


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    # Transform raw data frame into numeric feature matrix
    result = pd.DataFrame(index=df.index)

    # 1. One-hot encode decline reasons
    for val in DECLINE_REASON_VALUES:
        col_name = f"decline_reason_{val}"
        result[col_name] = (df["decline_reason"] == val).astype(int) if "decline_reason" in df.columns else 0

    # 2. One-hot encode payment methods
    for val in PAYMENT_METHOD_VALUES:
        col_name = f"payment_method_{val}"
        result[col_name] = (df["payment_method"] == val).astype(int) if "payment_method" in df.columns else 0

    # 3. Numeric conversions
    for col in BOOL_COLUMNS:
        result[col] = _coerce_bool(df[col]) if col in df.columns else 0

    for col in NUMERIC_COLUMNS:
        result[col] = pd.to_numeric(df[col], errors="coerce").fillna(0) if col in df.columns else 0

    feature_columns = list(result.columns)

    if TARGET_COLUMN in df.columns:
        result[TARGET_COLUMN] = _coerce_bool(df[TARGET_COLUMN])

    return result, feature_columns


def build_single_case_features(case: dict[str, Any], feature_columns: list[str]) -> pd.DataFrame:
    # Build aligned single-row feature frame for inference
    df = pd.DataFrame([case])
    features_df, _ = build_features(df)

    aligned = pd.DataFrame(columns=feature_columns)
    for col in feature_columns:
        if col in features_df.columns:
            aligned[col] = features_df[col].values
        else:
            aligned[col] = [0]

    return aligned