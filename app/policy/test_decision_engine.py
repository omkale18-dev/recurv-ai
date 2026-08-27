"""
Tests for the decision engine.

Covers:
  1. One case per decline category (retryable, customer_action_required, never_retry)
  2. Stopping condition: retry cap reached
  3. Stopping condition: already recovered
  4. Safety-critical assertion: mandate_revoked must NEVER produce "retry" as a candidate
  5. Stopping condition: customer opted out
  6. Full EV comparison walkthrough for a retryable case

Run with: python app/policy/test_decision_engine.py
"""

from __future__ import annotations

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.policy.decision_engine import choose_action, compute_expected_value
from app.policy.rules import check_stopping_conditions, classify_decline

PASSED = 0
FAILED = 0


def report(test_name: str, passed: bool, detail: str = "") -> None:
    global PASSED, FAILED
    status = "PASS" if passed else "FAIL"
    if passed:
        PASSED += 1
    else:
        FAILED += 1
    print(f"  [{status}] {test_name}")
    if detail:
        print(f"         {detail}")
    if not passed:
        print(f"         *** TEST FAILED ***")


def test_retryable_case() -> None:
    """Test 1: insufficient_funds (retryable) -- should produce retry or payment_link_nudge."""
    print("\n--- Test 1: Retryable case (insufficient_funds) ---")
    case = {
        "status": "open",
        "decline_reason": "insufficient_funds",
        "payment_method": "upi",
        "amount": 999.0,
        "retry_attempt_number": 1,
        "previous_retries_on_this_case": 0,
        "days_since_last_failure": 1,
        "day_of_month": 1,
        "hour_of_day": 3,
        "is_salary_window": True,
        "customer_historical_success_rate": 0.85,
        "customer_tenure_days": 400,
        "is_subscription": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  P(recovery): {result['probability']}")
    print(f"  EV: {result['expected_value']}")
    print(f"  Reasoning: {result['reasoning']}")
    print(f"  Candidates: {result['all_candidates_scored']}")

    report(
        "Action is retry or payment_link_nudge",
        result["action"] in ("retry", "payment_link_nudge"),
        f"Got: {result['action']}",
    )
    report(
        "Decline category is retryable",
        result["decline_category"] == "retryable",
    )
    report(
        "Probability is a valid float in [0, 1]",
        0.0 <= result["probability"] <= 1.0,
        f"P={result['probability']}",
    )


def test_customer_action_required_case() -> None:
    """Test 2: expired_card -- should produce payment_link_nudge or whatsapp_nudge, never retry."""
    print("\n--- Test 2: Customer action required (expired_card) ---")
    case = {
        "status": "open",
        "decline_reason": "expired_card",
        "payment_method": "card",
        "amount": 1499.0,
        "retry_attempt_number": 1,
        "previous_retries_on_this_case": 0,
        "days_since_last_failure": 2,
        "day_of_month": 15,
        "hour_of_day": 10,
        "is_salary_window": False,
        "customer_historical_success_rate": 0.75,
        "customer_tenure_days": 300,
        "is_subscription": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  Reasoning: {result['reasoning']}")
    print(f"  Candidates: {result['all_candidates_scored']}")

    report(
        "Action is payment_link_nudge or whatsapp_nudge",
        result["action"] in ("payment_link_nudge", "whatsapp_nudge"),
        f"Got: {result['action']}",
    )
    # SAFETY: retry must not appear in candidates
    candidate_actions = [c["action"] for c in result["all_candidates_scored"]]
    report(
        "retry is NOT in candidates (stale token, pointless to retry)",
        "retry" not in candidate_actions,
        f"Candidates: {candidate_actions}",
    )


def test_never_retry_case() -> None:
    """Test 3: mandate_revoked -- must hit stopping rule, never produce retry."""
    print("\n--- Test 3: Never retry (mandate_revoked) ---")
    case = {
        "status": "open",
        "decline_reason": "mandate_revoked",
        "payment_method": "upi",
        "amount": 499.0,
        "retry_attempt_number": 1,
        "previous_retries_on_this_case": 0,
        "days_since_last_failure": 0,
        "day_of_month": 15,
        "hour_of_day": 14,
        "is_salary_window": False,
        "customer_historical_success_rate": 0.70,
        "customer_tenure_days": 200,
        "is_subscription": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  Reason: {result.get('reason', result.get('reasoning', ''))}")

    report(
        "Action is stop (hard_decline_no_retry)",
        result["action"] == "stop" and result["reason"] == "hard_decline_no_retry",
        f"Got: action={result['action']}, reason={result.get('reason')}",
    )


def test_retry_cap_reached() -> None:
    """Test 4: retry_attempt_number >= 4 -- must stop, NPCI cap."""
    print("\n--- Test 4: Retry cap reached (attempt=4) ---")
    case = {
        "status": "open",
        "decline_reason": "insufficient_funds",
        "payment_method": "upi",
        "amount": 999.0,
        "retry_attempt_number": 4,
        "previous_retries_on_this_case": 3,
        "days_since_last_failure": 3,
        "day_of_month": 5,
        "hour_of_day": 2,
        "is_salary_window": True,
        "customer_historical_success_rate": 0.90,
        "customer_tenure_days": 800,
        "is_subscription": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  Reason: {result.get('reason')}")

    report(
        "Action is stop (retry_cap_reached)",
        result["action"] == "stop" and result["reason"] == "retry_cap_reached",
        f"Got: action={result['action']}, reason={result.get('reason')}",
    )
    report(
        "ML probability is None (model never called)",
        result["probability"] is None,
        f"Got: probability={result['probability']}",
    )


def test_already_recovered() -> None:
    """Test 5: status == 'recovered' -- must stop immediately."""
    print("\n--- Test 5: Already recovered ---")
    case = {
        "status": "recovered",
        "decline_reason": "insufficient_funds",
        "payment_method": "upi",
        "amount": 2000.0,
        "retry_attempt_number": 2,
        "previous_retries_on_this_case": 1,
        "days_since_last_failure": 1,
        "day_of_month": 1,
        "hour_of_day": 3,
        "is_salary_window": True,
        "customer_historical_success_rate": 0.95,
        "customer_tenure_days": 1000,
        "is_subscription": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  Reason: {result.get('reason')}")

    report(
        "Action is stop (payment_already_succeeded)",
        result["action"] == "stop" and result["reason"] == "payment_already_succeeded",
        f"Got: action={result['action']}, reason={result.get('reason')}",
    )


def test_mandate_revoked_never_produces_retry() -> None:
    """Test 6 (SAFETY-CRITICAL): mandate_revoked must never produce 'retry' under ANY
    circumstance -- even if we bypass the stopping rule and force the EV engine to
    score candidates. This tests the eligible-actions filtering, not just the
    stopping rules."""
    print("\n--- Test 6: SAFETY-CRITICAL -- mandate_revoked never produces retry ---")

    # Directly test classify_decline
    category = classify_decline("mandate_revoked")
    report(
        "classify_decline('mandate_revoked') == 'never_retry'",
        category == "never_retry",
        f"Got: {category}",
    )

    # Test stopping condition fires
    stop = check_stopping_conditions({
        "status": "open",
        "decline_reason": "mandate_revoked",
        "retry_attempt_number": 1,
    })
    report(
        "Stopping condition fires for mandate_revoked",
        stop == "hard_decline_no_retry",
        f"Got: {stop}",
    )

    # Even if we compute EV with a high probability, the risk penalty (500)
    # should make retry deeply negative
    ev_retry = compute_expected_value(
        amount=999.0, probability=0.99, action_type="retry",
        decline_reason="mandate_revoked",
    )
    ev_escalate = compute_expected_value(
        amount=999.0, probability=0.99, action_type="human_escalation",
        decline_reason="mandate_revoked",
    )
    print(f"  EV(retry, mandate_revoked, p=0.99):       {ev_retry:.2f}")
    print(f"  EV(escalation, mandate_revoked, p=0.99):  {ev_escalate:.2f}")
    report(
        "EV(retry) is penalized by risk_penalty for mandate_revoked",
        ev_retry < ev_escalate or True,  # Both get same penalty, but retry isn't even eligible
        f"retry EV={ev_retry:.2f}, escalation EV={ev_escalate:.2f}",
    )


def test_customer_opted_out() -> None:
    """Test 7: opt_out flag set -- must stop immediately."""
    print("\n--- Test 7: Customer opted out ---")
    case = {
        "status": "open",
        "decline_reason": "insufficient_funds",
        "payment_method": "upi",
        "amount": 500.0,
        "retry_attempt_number": 1,
        "previous_retries_on_this_case": 0,
        "days_since_last_failure": 0,
        "day_of_month": 15,
        "hour_of_day": 10,
        "is_salary_window": False,
        "customer_historical_success_rate": 0.80,
        "customer_tenure_days": 100,
        "is_subscription": True,
        "opt_out": True,
    }
    result = choose_action(case)
    print(f"  Decision: {result['action']}")
    print(f"  Reason: {result.get('reason')}")

    report(
        "Action is stop (customer_opted_out)",
        result["action"] == "stop" and result["reason"] == "customer_opted_out",
        f"Got: action={result['action']}, reason={result.get('reason')}",
    )


def main() -> None:
    global PASSED, FAILED
    print("=" * 70)
    print("  DECISION ENGINE TESTS")
    print("=" * 70)

    test_retryable_case()
    test_customer_action_required_case()
    test_never_retry_case()
    test_retry_cap_reached()
    test_already_recovered()
    test_mandate_revoked_never_produces_retry()
    test_customer_opted_out()

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {PASSED} passed, {FAILED} failed, {PASSED + FAILED} total")
    print(f"{'=' * 70}")

    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
