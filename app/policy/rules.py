from __future__ import annotations

from app.policy.constants import NPCI_MAX_TOTAL_ATTEMPTS

# Map decline reasons to recovery action categories
_DECLINE_CATEGORY_MAP: dict[str, str] = {
    "insufficient_funds": "retryable",
    "bank_timeout": "retryable",
    "generic_decline": "retryable",
    "expired_card": "customer_action_required",
    "auth_required": "customer_action_required",
    "mandate_revoked": "never_retry",
}


def classify_decline(decline_reason: str) -> str:
    # Conservative fallback: treat unknown declines as customer action required
    return _DECLINE_CATEGORY_MAP.get(decline_reason, "customer_action_required")


def check_stopping_conditions(case: dict) -> str | None:
    # Stop if payment is already recovered
    if case.get("status") == "recovered":
        return "payment_already_succeeded"

    # Stop if customer opted out
    if case.get("opt_out", False):
        return "customer_opted_out"

    # Stop if NPCI retry limit is reached
    if case.get("retry_attempt_number", 0) >= NPCI_MAX_TOTAL_ATTEMPTS:
        return "retry_cap_reached"

    # Stop if decline is strictly non-retryable
    if classify_decline(case.get("decline_reason", "")) == "never_retry":
        return "hard_decline_no_retry"

    return None