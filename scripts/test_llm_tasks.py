"""
Test script for LLM tasks: promise extraction + message drafting.

Runs 5 test messages through extract_promise_to_pay() and generates
6 recovery messages (one per decline_reason) via draft_recovery_message().
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ml.llm_tasks import extract_promise_to_pay, draft_recovery_message


def test_promise_extraction():
    print("=" * 75)
    print("  TEST: extract_promise_to_pay()")
    print("=" * 75)

    case_context = {
        "today": "2026-08-27",
        "amount": 999.0,
    }

    test_messages = [
        {
            "label": "1. Clear promise with specific date",
            "message": "Haan bhai, Friday ko payment kar dunga pakka. Salary aa jayegi tab tak.",
        },
        {
            "label": "2. Vague promise (no specific date)",
            "message": "I will try to pay soon, just give me some time please.",
        },
        {
            "label": "3. Opt-out request",
            "message": "Please stop messaging me. I don't want this subscription anymore. Cancel kar do.",
        },
        {
            "label": "4. Already-paid claim",
            "message": "Maine kal hi pay kar diya tha, check karo apne system mein. UPI se bheja tha.",
        },
        {
            "label": "5. Irrelevant / complaint message",
            "message": "Your app keeps crashing and customer support is terrible. Fix your product first.",
        },
    ]

    for test in test_messages:
        print(f"\n--- {test['label']} ---")
        print(f"  Message: \"{test['message']}\"")
        result = extract_promise_to_pay(test["message"], case_context)
        if result:
            print(f"  Result:")
            print(f"    promise_date:      {result.get('promise_date')}")
            print(f"    promise_amount:    {result.get('promise_amount')}")
            print(f"    confidence:        {result.get('confidence')}")
            print(f"    detected_opt_out:  {result.get('detected_opt_out')}")
            print(f"    already_paid_claim:{result.get('already_paid_claim')}")
            summary_safe = str(result.get('summary', '')).encode('ascii', errors='replace').decode('ascii')
            print(f"    summary:           {summary_safe}")
        else:
            print(f"  Result: None (parse failure)")


def test_message_drafting():
    print(f"\n\n{'=' * 75}")
    print("  TEST: draft_recovery_message()")
    print("=" * 75)

    decline_reasons = [
        "insufficient_funds",
        "bank_timeout",
        "expired_card",
        "mandate_revoked",
        "auth_required",
        "generic_decline",
    ]

    for reason in decline_reasons:
        case = {
            "decline_reason": reason,
            "amount": 999.0,
            "retry_attempt_number": 2,
            "payment_method": "upi" if reason in ("mandate_revoked", "insufficient_funds") else "card",
        }
        print(f"\n--- {reason} ({case['payment_method']}) ---")
        message = draft_recovery_message(case, language="hinglish")
        # Sanitize for Windows cp1252 terminal
        safe_msg = message.encode("ascii", errors="replace").decode("ascii")
        print(f"  Message: {safe_msg}")


if __name__ == "__main__":
    test_promise_extraction()
    test_message_drafting()
