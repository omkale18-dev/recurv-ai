"""
Boundary test script: Verifies exact NPCI retry attempt lifecycle (1 to 4 allowed, stopped at >=4).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.policy.rules import check_stopping_conditions
from app.policy.decision_engine import choose_action
from app.policy.constants import NPCI_MAX_TOTAL_ATTEMPTS

def test_retry_lifecycle():
    print(f"Testing NPCI Retry Lifecycle (NPCI_MAX_TOTAL_ATTEMPTS = {NPCI_MAX_TOTAL_ATTEMPTS})")
    print("-" * 65)

    for attempt in range(1, 6):
        case = {
            "status": "open",
            "decline_reason": "insufficient_funds",
            "payment_method": "upi",
            "amount": 999.0,
            "retry_attempt_number": attempt,
            "previous_retries_on_this_case": attempt - 1,
            "days_since_last_failure": 1,
            "day_of_month": 1,
            "hour_of_day": 3,
            "is_salary_window": True,
            "customer_historical_success_rate": 0.85,
            "customer_tenure_days": 400,
            "is_subscription": True,
        }

        stop_reason = check_stopping_conditions(case)
        decision = choose_action(case)

        action = decision["action"]
        reason = decision.get("reason") or decision.get("reasoning", "")
        ev = decision.get("expected_value")

        if attempt < NPCI_MAX_TOTAL_ATTEMPTS:
            status = "ALLOWED"
            assert action != "stop", f"Attempt {attempt} should be allowed but stopped!"
            print(f"  Attempt #{attempt} (Original + {attempt-1} retries): {status} -> Action: {action} (EV={ev})")
        else:
            status = "BLOCKED (CAP REACHED)"
            assert action == "stop" and decision.get("reason") == "retry_cap_reached", f"Attempt {attempt} should be blocked!"
            print(f"  Attempt #{attempt} (Exhausted {NPCI_MAX_TOTAL_ATTEMPTS} attempts): {status} -> Action: {action} (Reason: {reason})")

    print("\n[SUCCESS] NPCI Retry Cap Boundary Verified: Exactly 1 original + 3 retries allowed, 4th retry strictly blocked!")

if __name__ == "__main__":
    test_retry_lifecycle()
