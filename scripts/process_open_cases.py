"""
CLI script to process all open recovery cases.

Queries all Case rows with status="open", runs each through the decision
engine + executor pipeline, and prints a summary table.

Usage:
    python scripts/process_open_cases.py
"""

from __future__ import annotations

import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.db import Case, Action, AuditLog, SessionLocal, init_db
from app.policy.executor import execute_case

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    init_db()
    db = SessionLocal()

    try:
        open_cases = db.query(Case).filter(Case.status == "open").all()

        if not open_cases:
            print("\nNo open cases found. Nothing to process.")
            print("Hint: insert a test case or trigger a payment.failed webhook.")
            return

        print(f"\nFound {len(open_cases)} open case(s). Processing...\n")
        print(f"{'Case ID':>8}  {'Decline Reason':<22}  {'Amount':>10}  {'Action':<22}  {'Outcome':<26}  {'EV'}")
        print(f"{'-' * 110}")

        for case in open_cases:
            action_row = execute_case(db, case)

            if action_row:
                # Fetch the reasoning to extract EV (stored in reason field)
                ev_str = ""
                if action_row.reason and "EV=" in action_row.reason:
                    # Extract EV from reasoning string
                    try:
                        ev_part = action_row.reason.split("EV=")[1].split(")")[0]
                        ev_str = f"EV={ev_part}"
                    except (IndexError, ValueError):
                        ev_str = ""

                print(
                    f"{case.id:>8}  {case.decline_reason or 'unknown':<22}  "
                    f"{case.amount or 0:>10.2f}  {action_row.action_type:<22}  "
                    f"{action_row.outcome or 'unknown':<26}  {ev_str}"
                )
            else:
                print(
                    f"{case.id:>8}  {case.decline_reason or 'unknown':<22}  "
                    f"{case.amount or 0:>10.2f}  {'(no action)':<22}  "
                    f"{'(none)':<26}"
                )

        # Print summary
        print(f"\n{'=' * 110}")
        print(f"Processed {len(open_cases)} case(s).")

        # Show recent audit log entries
        recent_audits = (
            db.query(AuditLog)
            .order_by(AuditLog.id.desc())
            .limit(len(open_cases) * 2)
            .all()
        )
        if recent_audits:
            print(f"\nRecent Audit Log Entries (last {len(recent_audits)}):")
            print(f"{'-' * 110}")
            for audit in reversed(recent_audits):
                print(
                    f"  [{audit.timestamp}] Case #{audit.case_id or '-'}: "
                    f"{audit.description}"
                )
                if audit.reason:
                    # Truncate long reasons for display
                    reason_display = audit.reason[:200]
                    if len(audit.reason) > 200:
                        reason_display += "..."
                    print(f"    Reason: {reason_display}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
