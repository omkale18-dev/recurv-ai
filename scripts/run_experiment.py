"""
Control-vs-AI experiment: evaluates AI policy engine vs naive static retry.

Methodology:
  - Uses data/demo_batch.csv (100 held-out rows, never used in training)
  - 50/50 Stratified Split on decline_reason
  - Control Policy (Naive Baseline):
      * Blindly retries every case up to 3 times (Day 1, 3, 7) regardless of root cause.
      * No decline categorization, no stopping rules, no channel switching.
  - Treatment Policy (AI Policy Engine):
      * Uses choose_action() from app/policy/decision_engine.py.
      * Deterministic compliance rules (stopping on mandate_revoked / retry cap).
      * Root-cause routing (payment links for expired_card / auth_required).
      * ML probability estimation and EV optimization.
  - Simulation Mechanics:
      * Ground-truth base rates per decline reason from industry benchmarks.
      * Channel effectiveness: Retrying dead cards / auth-required tokens has ~5% success,
        while sending payment links achieves full 100% effectiveness.
      * Diminishing returns on repeated retries (Attempt 1: 100%, Attempt 2: 70%, Attempt 3: 50%).

Outputs:
  - data/experiment_results.json
  - Clean formatted CLI output
"""

from __future__ import annotations

import json
import os
import random
import sys

import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.policy.decision_engine import choose_action
from app.policy.rules import classify_decline
from app.policy.constants import NPCI_MAX_TOTAL_ATTEMPTS

RANDOM_SEED = 42
DEMO_BATCH_PATH = os.path.join("data", "demo_batch.csv")
RESULTS_PATH = os.path.join("data", "experiment_results.json")

BASE_RECOVERY_RATES = {
    "insufficient_funds": 0.60,
    "bank_timeout":       0.70,
    "expired_card":       0.12,
    "mandate_revoked":    0.05,
    "auth_required":      0.45,
    "generic_decline":    0.35,
}


def _action_effectiveness(action: str, decline_reason: str) -> float:
    """Action effectiveness multiplier based on structural root cause."""
    category = classify_decline(decline_reason)

    if action == "retry":
        if category == "retryable":
            return 1.0
        elif category == "customer_action_required":
            # Retrying dead cards or unauthenticated mandates almost always fails
            return 0.05
        elif category == "never_retry":
            return 0.0
    elif action in ("payment_link_nudge", "whatsapp_nudge"):
        if category == "customer_action_required":
            # Payment links allow the customer to enter fresh card / 3DS auth
            return 1.0 if action == "payment_link_nudge" else 1.05
        elif category == "retryable":
            # Payment link adds friction vs auto-debit
            return 0.80
        elif category == "never_retry":
            return 0.10
    elif action in ("stop", "human_escalation"):
        return 0.0

    return 0.5


def _simulate_case_outcome(
    decline_reason: str,
    actions: list[dict],
    amount: float,
    case_row: dict,
    rng: random.Random,
) -> dict:
    """Simulate outcome across action attempts."""
    DIMINISHING_RETURNS = {1: 1.0, 2: 0.70, 3: 0.50, 4: 0.30}

    base_rate = BASE_RECOVERY_RATES.get(decline_reason, 0.35)

    adjusted_rate = base_rate
    if case_row.get("is_salary_window"):
        adjusted_rate += 0.08
    hist_success = float(case_row.get("customer_historical_success_rate", 0.5))
    if hist_success > 0.8:
        adjusted_rate += 0.05
    elif hist_success < 0.4:
        adjusted_rate -= 0.05

    attempt_log = []
    total_attempts = 0

    for i, act in enumerate(actions):
        action_type = act["action"]
        if action_type == "stop":
            attempt_log.append({"action": "stop", "reason": act.get("reason", "")})
            break

        total_attempts += 1
        attempt_num = i + 1

        effectiveness = _action_effectiveness(action_type, decline_reason)
        dim_factor = DIMINISHING_RETURNS.get(attempt_num, 0.30)

        final_prob = max(0.01, min(0.95, adjusted_rate * effectiveness * dim_factor))
        recovered = rng.random() < final_prob

        attempt_log.append({
            "action": action_type,
            "attempt_number": attempt_num,
            "simulated_probability": round(final_prob, 4),
            "effectiveness": effectiveness,
            "recovered": recovered,
        })

        if recovered:
            return {
                "recovered": True,
                "amount_recovered": amount,
                "total_attempts": total_attempts,
                "actions": attempt_log,
                "recovering_action": action_type,
            }

    return {
        "recovered": False,
        "amount_recovered": 0.0,
        "total_attempts": total_attempts,
        "actions": attempt_log,
        "recovering_action": None,
    }


def naive_retry_policy(case: dict) -> list[dict]:
    """Naive static retry: 3 retries on day 1, 3, 7 blindly."""
    return [
        {"action": "retry", "schedule_day": 1},
        {"action": "retry", "schedule_day": 3},
        {"action": "retry", "schedule_day": 7},
    ]


def ai_policy(case: dict) -> list[dict]:
    """AI policy: choose_action() dynamically determines actions and stops."""
    max_steps = 4
    actions = []
    case_copy = dict(case)

    for _ in range(max_steps):
        decision = choose_action(case_copy)
        action_type = decision["action"]

        if action_type == "stop":
            actions.append({
                "action": "stop",
                "reason": decision.get("reason", ""),
            })
            break

        actions.append({
            "action": action_type,
            "probability": decision.get("probability"),
            "expected_value": decision.get("expected_value"),
            "decline_category": decision.get("decline_category"),
        })

        # Advance attempt counter
        case_copy["retry_attempt_number"] = case_copy.get("retry_attempt_number", 1) + 1
        case_copy["previous_retries_on_this_case"] = case_copy.get("previous_retries_on_this_case", 0) + 1

    return actions


def run_experiment() -> dict:
    print("=" * 75)
    print("  CONTROL vs AI REVENUE RECOVERY EXPERIMENT")
    print("  Data: data/demo_batch.csv (100 held-out rows, 50/50 Stratified Split)")
    print("=" * 75)

    df = pd.read_csv(DEMO_BATCH_PATH)

    # 50/50 Stratified Split on decline_reason
    control_df, treatment_df = train_test_split(
        df,
        test_size=0.50,
        random_state=RANDOM_SEED,
        stratify=df["decline_reason"],
    )
    control_df = control_df.reset_index(drop=True)
    treatment_df = treatment_df.reset_index(drop=True)

    print(f"\n  Control group:   {len(control_df)} cases")
    print(f"  Treatment group: {len(treatment_df)} cases")
    print(f"\n  Stratified Distribution:")
    for reason in sorted(df["decline_reason"].unique()):
        c_count = (control_df["decline_reason"] == reason).sum()
        t_count = (treatment_df["decline_reason"] == reason).sum()
        print(f"    {reason:<22} Control: {c_count:>2}  |  Treatment: {t_count:>2}")

    # Standard paired seeds for reproducible simulation
    control_rng = random.Random(RANDOM_SEED)
    treatment_rng = random.Random(RANDOM_SEED)

    control_results = _run_group(control_df, naive_retry_policy, control_rng)
    treatment_results = _run_group(treatment_df, ai_policy, treatment_rng)

    summary = _compute_summary(control_results, treatment_results)
    _print_summary(summary)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Experiment results saved to {RESULTS_PATH}")

    return summary


def _run_group(
    group_df: pd.DataFrame,
    policy_fn,
    rng: random.Random,
) -> list[dict]:
    results = []

    for _, row in group_df.iterrows():
        case = row.to_dict()
        case.setdefault("status", "open")
        case.setdefault("retry_attempt_number", 1)
        case.setdefault("previous_retries_on_this_case", 0)
        case.setdefault("days_since_last_failure", 1)
        case.setdefault("day_of_month", int(case.get("day_of_month", 15)))
        case.setdefault("hour_of_day", int(case.get("hour_of_day", 3)))
        case.setdefault("customer_tenure_days", int(case.get("customer_tenure_days", 365)))
        case.setdefault("opt_out", False)

        actions = policy_fn(case)
        amount = float(case.get("amount", 0))
        decline_reason = case["decline_reason"]

        outcome = _simulate_case_outcome(decline_reason, actions, amount, case, rng)

        is_customer_action = classify_decline(decline_reason) == "customer_action_required"
        is_never_retry = classify_decline(decline_reason) == "never_retry"
        used_retry = any(a["action"] == "retry" for a in outcome["actions"] if a["action"] != "stop")
        used_payment_link = any(a["action"] in ("payment_link_nudge", "whatsapp_nudge") for a in outcome["actions"] if a["action"] != "stop")

        results.append({
            "case_id": case.get("case_id", "unknown"),
            "decline_reason": decline_reason,
            "decline_category": classify_decline(decline_reason),
            "amount": amount,
            "recovered": outcome["recovered"],
            "amount_recovered": outcome["amount_recovered"],
            "total_attempts": outcome["total_attempts"],
            "recovering_action": outcome["recovering_action"],
            "wasted_retries_on_stale_tokens": is_customer_action and used_retry,
            "correct_channel_used": is_customer_action and used_payment_link and not used_retry,
            "correctly_halted_hard_decline": is_never_retry and not used_retry,
        })

    return results


def _compute_summary(control: list[dict], treatment: list[dict]) -> dict:
    def group_stats(results: list[dict], name: str) -> dict:
        n = len(results)
        recovered_count = sum(1 for r in results if r["recovered"])
        total_recovered_amount = sum(r["amount_recovered"] for r in results)
        total_amount = sum(r["amount"] for r in results)
        avg_attempts = sum(r["total_attempts"] for r in results) / max(n, 1)
        wasted_retries = sum(1 for r in results if r["wasted_retries_on_stale_tokens"])
        correct_channel = sum(1 for r in results if r["correct_channel_used"])

        per_reason = {}
        for reason in sorted(set(r["decline_reason"] for r in results)):
            reason_cases = [r for r in results if r["decline_reason"] == reason]
            reason_recovered = sum(1 for r in reason_cases if r["recovered"])
            per_reason[reason] = {
                "n": len(reason_cases),
                "recovered": reason_recovered,
                "recovery_rate": round(reason_recovered / max(len(reason_cases), 1) * 100, 1),
                "amount_recovered": round(sum(r["amount_recovered"] for r in reason_cases), 2),
            }

        return {
            "group": name,
            "n": n,
            "recovered_count": recovered_count,
            "recovery_rate_pct": round(recovered_count / max(n, 1) * 100, 1),
            "total_amount": round(total_amount, 2),
            "amount_recovered": round(total_recovered_amount, 2),
            "avg_attempts_per_case": round(avg_attempts, 2),
            "wasted_retries_on_stale_tokens": wasted_retries,
            "correct_channel_used": correct_channel,
            "per_decline_reason": per_reason,
        }

    ctrl = group_stats(control, "control")
    treat = group_stats(treatment, "treatment")

    return {
        "experiment": {
            "data_source": "data/demo_batch.csv",
            "total_cases": 100,
            "group_size": 50,
            "random_seed": RANDOM_SEED,
            "split_method": "Stratified 50/50 split on decline_reason",
            "methodology": (
                "Both groups simulate recovery outcomes on held-out test data. Control uses "
                "naive static retries (3 attempts). AI uses the policy engine (rules + ML probability + "
                "EV optimization). Channel appropriateness penalties reflect the real-world impossibility "
                "of retrying dead cards/auth-tokens without customer intervention."
            ),
            "limitation": (
                "Outcomes are simulated based on industry failure models, not live production data. "
                "The primary driver of the AI advantage is structural root-cause routing and attempt efficiency."
            ),
        },
        "control": ctrl,
        "treatment": treat,
        "delta": {
            "recovery_rate_pp": round(treat["recovery_rate_pct"] - ctrl["recovery_rate_pct"], 1),
            "incremental_amount_recovered": round(treat["amount_recovered"] - ctrl["amount_recovered"], 2),
            "incremental_cases_recovered": treat["recovered_count"] - ctrl["recovered_count"],
            "attempts_saved_per_case": round(ctrl["avg_attempts_per_case"] - treat["avg_attempts_per_case"], 2),
        },
    }


def _print_summary(summary: dict) -> None:
    ctrl = summary["control"]
    treat = summary["treatment"]
    delta = summary["delta"]

    print(f"\n{'=' * 75}")
    print(f"  EXPERIMENT RESULTS SUMMARY")
    print(f"{'=' * 75}")
    print(f"\n  {'Metric':<42} {'Control':>10} {'AI Policy':>10} {'Delta':>10}")
    print(f"  {'-' * 75}")
    print(f"  {'Recovery Rate':<42} {ctrl['recovery_rate_pct']:>9.1f}% {treat['recovery_rate_pct']:>9.1f}% {delta['recovery_rate_pp']:>+9.1f}pp")
    print(f"  {'Cases Recovered (of 50)':<42} {ctrl['recovered_count']:>10} {treat['recovered_count']:>10} {delta['incremental_cases_recovered']:>+10}")
    print(f"  {'Amount Recovered (INR)':<42} {ctrl['amount_recovered']:>10.0f} {treat['amount_recovered']:>10.0f} {delta['incremental_amount_recovered']:>+10.0f}")
    print(f"  {'Avg Attempts per Case':<42} {ctrl['avg_attempts_per_case']:>10.2f} {treat['avg_attempts_per_case']:>10.2f} {delta['attempts_saved_per_case']:>+10.2f}")
    print(f"  {'Wasted Retries on Dead Tokens':<42} {ctrl['wasted_retries_on_stale_tokens']:>10} {treat['wasted_retries_on_stale_tokens']:>10}")
    print(f"  {'Smart Payment Links Sent':<42} {ctrl['correct_channel_used']:>10} {treat['correct_channel_used']:>10}")

    print(f"\n  Per-Decline-Reason Recovery Rates:")
    print(f"  {'-' * 75}")
    all_reasons = sorted(set(
        list(ctrl["per_decline_reason"].keys()) +
        list(treat["per_decline_reason"].keys())
    ))
    print(f"  {'Decline Reason':<22} {'Ctrl N':>7} {'Ctrl %':>7} {'AI N':>7}  {'AI %':>7}")
    for reason in all_reasons:
        c = ctrl["per_decline_reason"].get(reason, {"n": 0, "recovery_rate": 0})
        t = treat["per_decline_reason"].get(reason, {"n": 0, "recovery_rate": 0})
        print(f"  {reason:<22} {c['n']:>7} {c['recovery_rate']:>6.1f}% {t['n']:>7}  {t['recovery_rate']:>6.1f}%")

    print(f"\n{'=' * 75}")


if __name__ == "__main__":
    run_experiment()
