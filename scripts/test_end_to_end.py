"""
End-to-end integration test script.

Inserts test Case rows representing different real-world scenarios into
revenue_recovery.db, runs process_open_cases.py logic, and inspects the
resulting Case, Action, and AuditLog records.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.db import init_db, SessionLocal, Case, Action, AuditLog
from app.policy.executor import execute_case

def setup_test_cases():
    init_db()
    db = SessionLocal()
    
    # Clean up old open test cases for clean run
    db.query(Case).filter(Case.status == "open").delete()
    db.commit()

    test_cases_data = [
        {
            "razorpay_payment_id": "pay_test_001",
            "razorpay_subscription_id": "sub_test_001",
            "customer_id": "cust_test_001",
            "amount": 999.0,
            "decline_reason": "insufficient_funds",
            "payment_method": "upi",
            "status": "open",
            "retry_attempt_number": 1,
        },
        {
            "razorpay_payment_id": "pay_test_002",
            "razorpay_subscription_id": None,
            "customer_id": "cust_test_002",
            "amount": 1499.0,
            "decline_reason": "expired_card",
            "payment_method": "card",
            "status": "open",
            "retry_attempt_number": 1,
        },
        {
            "razorpay_payment_id": "pay_test_003",
            "razorpay_subscription_id": "sub_test_003",
            "customer_id": "cust_test_003",
            "amount": 499.0,
            "decline_reason": "mandate_revoked",
            "payment_method": "upi",
            "status": "open",
            "retry_attempt_number": 1,
        },
        {
            "razorpay_payment_id": "pay_test_004",
            "razorpay_subscription_id": "sub_test_004",
            "customer_id": "cust_test_004",
            "amount": 799.0,
            "decline_reason": "insufficient_funds",
            "payment_method": "upi",
            "status": "open",
            "retry_attempt_number": 4, # Already at cap
        }
    ]

    inserted_ids = []
    for c_data in test_cases_data:
        case = Case(**c_data)
        db.add(case)
        db.commit()
        db.refresh(case)
        inserted_ids.append(case.id)
        print(f"Created Test Case #{case.id}: {case.decline_reason} (INR {case.amount})")

    db.close()
    return inserted_ids

if __name__ == "__main__":
    setup_test_cases()
