"""
Case execution orchestrator.

This is the main loop that turns a decision_engine.choose_action() output into
a real (or simulated) recovery action, updates the database, and writes the
audit trail.

Execution order:
  1. Build case feature dict from the Case DB row
  2. Call decision_engine.choose_action() -> decision dict
  3. If action == "stop": record stop, return
  4. Enforce NPCI execution window for retry actions
  5. Dispatch to the appropriate Razorpay action wrapper
  6. Update Case row (retry count, status)
  7. Write Action row and AuditLog entry
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.db import Action, Case, write_audit_log
from app.policy.constants import NPCI_EXECUTION_WINDOW
from app.policy.decision_engine import choose_action
from app.razorpay_client.actions import (
    create_recovery_payment_link,
    escalate_to_human,
    retry_charge,
)

logger = logging.getLogger(__name__)

# IST is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))


def _case_to_feature_dict(case: Case) -> dict[str, Any]:
    """Convert a Case ORM row into the dict format expected by the decision engine."""
    return {
        "status": case.status or "open",
        "decline_reason": case.decline_reason or "",
        "payment_method": case.payment_method or "",
        "amount": float(case.amount or 0),
        "retry_attempt_number": int(case.retry_attempt_number or 0),
        "previous_retries_on_this_case": max(0, int(case.retry_attempt_number or 0) - 1),
        "days_since_last_failure": 0,  # Computed from timestamps in production
        "day_of_month": (case.created_at or datetime.utcnow()).day,
        "hour_of_day": (case.created_at or datetime.utcnow()).hour,
        "is_salary_window": (
            (case.created_at or datetime.utcnow()).day >= 28
            or (case.created_at or datetime.utcnow()).day <= 3
        ),
        "customer_historical_success_rate": 0.70,  # Default; would come from customer profile DB
        "customer_tenure_days": 365,  # Default; would come from customer profile DB
        "is_subscription": bool(case.razorpay_subscription_id),
        "opt_out": False,  # Would come from customer preferences DB
        # IDs for action dispatch
        "razorpay_subscription_id": case.razorpay_subscription_id or "",
        "razorpay_payment_id": case.razorpay_payment_id or "",
        "customer_id": case.customer_id or "",
    }


def _is_in_npci_window() -> bool:
    """Check if the current IST hour is within the NPCI execution window."""
    now_ist = datetime.now(IST)
    start, end = NPCI_EXECUTION_WINDOW
    return start <= now_ist.hour < end


def execute_case(db: Session, case: Case) -> Action | None:
    """Execute the full decision-and-action loop for a single case.

    Parameters
    ----------
    db : Session
        Active SQLAlchemy session.
    case : Case
        The case to process. Must have status="open".

    Returns
    -------
    Action | None
        The Action row created, or None if no action was taken.
    """
    case_dict = _case_to_feature_dict(case)

    # ----- Step 1: Get the decision -----
    decision = choose_action(case_dict)
    action_type = decision["action"]

    # ----- Step 2: Handle STOP decisions -----
    if action_type == "stop":
        stop_reason = decision.get("reason", "unknown_stop_reason")

        action_row = Action(
            case_id=case.id,
            action_type="stop",
            reason=stop_reason,
            outcome=stop_reason,
        )
        db.add(action_row)

        # Update case status based on stop reason
        if stop_reason == "payment_already_succeeded":
            case.status = "recovered"
        elif stop_reason in ("retry_cap_reached", "hard_decline_no_retry"):
            case.status = "escalated"
        elif stop_reason == "customer_opted_out":
            case.status = "closed"
        else:
            case.status = "closed"

        db.commit()
        db.refresh(action_row)

        write_audit_log(
            db,
            case_id=case.id,
            description=f"STOP: Case #{case.id} -- action halted",
            reason=(
                f"Stopping condition: {stop_reason}. "
                f"No ML model called, no recovery action dispatched. "
                f"Case status set to '{case.status}'."
            ),
        )

        logger.info("Case #%d: STOP (%s)", case.id, stop_reason)
        return action_row

    # ----- Step 3: Enforce NPCI execution window for retries -----
    if action_type == "retry" and not _is_in_npci_window():
        now_ist = datetime.now(IST)
        action_row = Action(
            case_id=case.id,
            action_type="retry",
            reason=decision.get("reasoning", ""),
            outcome="deferred_outside_window",
        )
        db.add(action_row)
        db.commit()
        db.refresh(action_row)

        write_audit_log(
            db,
            case_id=case.id,
            description=(
                f"DEFERRED: Case #{case.id} -- retry deferred, outside NPCI window"
            ),
            reason=(
                f"Decision engine chose 'retry' (EV={decision.get('expected_value')}), "
                f"but current IST hour is {now_ist.hour}:00, outside the NPCI "
                f"non-peak execution window ({NPCI_EXECUTION_WINDOW[0]}:00-"
                f"{NPCI_EXECUTION_WINDOW[1]}:00 IST). Retry will be attempted "
                f"in the next eligible window. P(recovery)={decision.get('probability')}."
            ),
        )

        logger.info(
            "Case #%d: retry DEFERRED (IST hour=%d, window=%s)",
            case.id, now_ist.hour, NPCI_EXECUTION_WINDOW,
        )
        return action_row

    # ----- Step 4: Dispatch the action -----
    reasoning = decision.get("reasoning", "")
    probability = decision.get("probability")
    ev = decision.get("expected_value")
    execution_result: dict[str, Any] = {}

    if action_type == "retry":
        sub_id = case_dict.get("razorpay_subscription_id", "")
        execution_result = retry_charge(sub_id)

    elif action_type == "payment_link_nudge":
        customer_contact = {
            "name": f"Customer {case_dict.get('customer_id', 'Unknown')}",
            "email": "customer@example.com",  # Would come from customer DB
            "contact": "",  # Would come from customer DB
        }
        execution_result = create_recovery_payment_link(
            amount=float(case.amount or 0),
            customer_contact=customer_contact,
            case_id=str(case.id),
        )

    elif action_type == "whatsapp_nudge":
        # WhatsApp Business API integration would go here.
        # For now, treated as a payment link with WhatsApp delivery channel.
        execution_result = {
            "action": "whatsapp_nudge",
            "simulated": True,
            "simulation_note": (
                "WhatsApp Business API integration not yet implemented. "
                "In production, this would send a payment link via WhatsApp."
            ),
            "outcome": "pending",
        }

    elif action_type == "human_escalation":
        execution_result = escalate_to_human(
            case_id=str(case.id),
            reason=reasoning,
        )

    else:
        logger.warning("Case #%d: unknown action type '%s'", case.id, action_type)
        execution_result = {"outcome": "unknown_action", "action": action_type}

    # ----- Step 5: Update Case row -----
    outcome = execution_result.get("outcome", "unknown")

    if action_type in ("retry", "payment_link_nudge"):
        case.retry_attempt_number = (case.retry_attempt_number or 0) + 1

    if action_type == "human_escalation":
        case.status = "escalated"

    # Mark case as in-progress (no longer sitting idle in "open")
    if case.status == "open":
        case.status = "in_progress"

    # ----- Step 6: Write Action row -----
    action_row = Action(
        case_id=case.id,
        action_type=action_type,
        reason=reasoning,
        outcome=outcome,
    )
    db.add(action_row)
    db.commit()
    db.refresh(action_row)

    # ----- Step 7: Write audit log -----
    # Build a detailed, self-contained audit entry
    candidates_summary = ""
    all_scored = decision.get("all_candidates_scored")
    if all_scored:
        candidates_summary = "; ".join(
            f"{c['action']}(EV={c['expected_value']})" for c in all_scored
        )

    is_simulated = execution_result.get("simulated", False)
    sim_note = " [SIMULATED]" if is_simulated else ""

    write_audit_log(
        db,
        case_id=case.id,
        description=(
            f"EXECUTED{sim_note}: Case #{case.id} -- "
            f"{action_type} (outcome={outcome})"
        ),
        reason=(
            f"P(recovery)={probability}, EV={ev}. "
            f"Candidates scored: [{candidates_summary}]. "
            f"Reasoning: {reasoning} "
            f"Execution result: {json.dumps(execution_result, default=str)}"
        ),
    )

    logger.info(
        "Case #%d: %s (outcome=%s, EV=%s, P=%s)%s",
        case.id, action_type, outcome, ev, probability, sim_note,
    )
    return action_row
