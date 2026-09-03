from __future__ import annotations

from typing import Any

from app.ml.predict import predict_recovery_probability
from app.policy.constants import ACTION_COSTS, RISK_PENALTIES
from app.policy.rules import check_stopping_conditions, classify_decline

# Actions allowed per decline category
_ELIGIBLE_ACTIONS: dict[str, list[str]] = {
    "retryable": ["retry", "payment_link_nudge"],
    "customer_action_required": ["payment_link_nudge", "whatsapp_nudge"],
    "never_retry": ["human_escalation"],
}


def compute_expected_value(
    amount: float,
    probability: float,
    action_type: str,
    decline_reason: str,
) -> float:
    # EV = (invoice_amount * P(recovery)) - action_cost - risk_penalty
    expected_revenue = amount * probability
    cost = ACTION_COSTS.get(action_type, 0.0)
    penalty = RISK_PENALTIES.get(decline_reason, 0.0)
    return expected_revenue - cost - penalty


def _build_reasoning(
    chosen_action: str,
    chosen_ev: float,
    all_scored: list[dict[str, Any]],
    decline_category: str,
    decline_reason: str,
) -> str:
    # Build human-readable reasoning string for audit trail
    if len(all_scored) == 1:
        only = all_scored[0]
        return f"Only eligible action for {decline_category} ({decline_reason}): {only['action']} with EV={only['expected_value']:.2f}."

    others = [s for s in all_scored if s["action"] != chosen_action]
    others_desc = ", ".join(f"{s['action']} (EV={s['expected_value']:.2f})" for s in others)
    return f"Chose {chosen_action} (EV={chosen_ev:.2f}) over {others_desc}. Category: {decline_category} ({decline_reason})."


def choose_action(case: dict) -> dict[str, Any]:
    # 1. Evaluate deterministic stopping rules
    stop_reason = check_stopping_conditions(case)
    if stop_reason is not None:
        return {
            "action": "stop",
            "reason": stop_reason,
            "expected_value": None,
            "probability": None,
            "decline_category": None,
            "all_candidates_scored": None,
        }

    # 2. Classify decline and fetch ML recovery probability
    decline_reason = case.get("decline_reason", "")
    decline_category = classify_decline(decline_reason)
    probability = predict_recovery_probability(case)

    # 3. Score all eligible candidate actions
    eligible_actions = _ELIGIBLE_ACTIONS.get(decline_category, ["human_escalation"])
    amount = float(case.get("amount", 0))

    scored_candidates: list[dict[str, Any]] = []
    for action_type in eligible_actions:
        ev = compute_expected_value(amount, probability, action_type, decline_reason)
        scored_candidates.append({
            "action": action_type,
            "expected_value": round(ev, 2),
            "cost": ACTION_COSTS.get(action_type, 0.0),
            "risk_penalty": RISK_PENALTIES.get(decline_reason, 0.0),
        })

    # 4. Pick candidate with highest expected value
    best = max(scored_candidates, key=lambda c: c["expected_value"])
    reasoning = _build_reasoning(
        chosen_action=best["action"],
        chosen_ev=best["expected_value"],
        all_scored=scored_candidates,
        decline_category=decline_category,
        decline_reason=decline_reason,
    )

    return {
        "action": best["action"],
        "expected_value": best["expected_value"],
        "probability": round(probability, 4),
        "decline_category": decline_category,
        "all_candidates_scored": scored_candidates,
        "reasoning": reasoning,
    }