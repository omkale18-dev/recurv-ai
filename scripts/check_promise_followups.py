"""
Check for missed promise-to-pay follow-ups.

Queries the promise_to_pay table for promises where:
  - promise_date has passed (relative to today)
  - fulfilled is still False
  - The linked case is not already recovered

These represent cases where a customer said "I'll pay by X" but didn't,
and should be escalated for manual follow-up or a second nudge.

Usage:
    python scripts/check_promise_followups.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.db import Case, PromiseToPay, SessionLocal, init_db, write_audit_log


def main() -> None:
    init_db()
    db = SessionLocal()

    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Minimum confidence to treat a promise as actionable for follow-up.
        # Below this, the LLM wasn't confident enough that the customer actually
        # committed to a date — escalating on a vague "I'll try soon" wastes
        # human agent time and annoys the customer.
        MIN_ACTIONABLE_CONFIDENCE = 0.6

        # Find all unfulfilled promises with a past promise_date
        overdue_promises = (
            db.query(PromiseToPay)
            .filter(
                PromiseToPay.fulfilled == False,
                PromiseToPay.promise_date != None,
                PromiseToPay.promise_date < today,
                PromiseToPay.confidence >= MIN_ACTIONABLE_CONFIDENCE,
            )
            .all()
        )

        if not overdue_promises:
            print(f"\nNo overdue promises found as of {today}.")
            print("All customer commitments are either fulfilled or not yet due.")
            return

        print(f"\n{'=' * 75}")
        print(f"  OVERDUE PROMISE-TO-PAY FOLLOW-UPS (as of {today})")
        print(f"{'=' * 75}")
        print(f"\n  {'Promise ID':>10}  {'Case ID':>8}  {'Promise Date':<14}  {'Amount':>10}  {'Confidence':>10}  {'Case Status':<12}")
        print(f"  {'-' * 75}")

        escalation_count = 0

        for promise in overdue_promises:
            case = db.query(Case).filter(Case.id == promise.case_id).first()
            case_status = case.status if case else "unknown"

            # Skip if case was already recovered (promise implicitly fulfilled)
            if case_status == "recovered":
                promise.fulfilled = True
                db.commit()
                continue

            escalation_count += 1
            amount_str = f"INR {promise.promise_amount:.0f}" if promise.promise_amount else "unspecified"

            print(
                f"  {promise.id:>10}  {promise.case_id:>8}  {promise.promise_date:<14}  "
                f"{amount_str:>10}  {promise.confidence:>9.0%}  {case_status:<12}"
            )

            if promise.llm_summary:
                print(f"             Summary: {promise.llm_summary}")

            # Write audit trail entry for the escalation
            write_audit_log(
                db,
                case_id=promise.case_id,
                description=f"MISSED PROMISE: Promise #{promise.id} overdue",
                reason=(
                    f"Customer promised to pay by {promise.promise_date} "
                    f"(amount: {amount_str}, confidence: {promise.confidence:.0%}). "
                    f"Date has passed and case status is '{case_status}'. "
                    f"Flagged for escalation or second nudge."
                ),
            )

        print(f"\n  {escalation_count} promise(s) flagged for follow-up escalation.")
        print(f"{'=' * 75}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
