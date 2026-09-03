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

# IST timezone helper
IST = timezone(timedelta(hours=5, minutes=30))


def _case_to_feature_dict(case: Case) -> dict[str, Any]:
    # Extract feature dictionary from case model
    return {
        "status": case.status or "open",
        "decline_reason": case.decline_reason or "",
        "payment_method": case.payment_method or "",
        "amount": float(case.amount or 0),
        "retry_attempt_number": int(case.retry_attempt_number or 0),
        "previous_retries_on_this_case": max(0, int(case.retry_attempt_number or 0) - 1),
        "days_since_last_failure": 0,
        "day_of_month": (case.created_at or datetime.utcnow()).day,
        "hour_of_day": (case.created_at or datetime.utcnow()).hour,
        "is_salary_window": (
            (case.created_at or datetime.utcnow()).day >= 28
            or (case.created_at or datetime.utcnow()).day <= 3
        ),
        "customer_historical_success_rate": 0.70,
        "customer_tenure_days": 365,
        "is_subscription": bool(case.razorpay_subscription_id),
        "opt_out": bool(getattr(case, "opt_out", False)),
        "razorpay_subscription_id": case.razorpay_subscription_id or "",
        "razorpay_payment_id": case.razorpay_payment_id or "",
        "customer_id": case.customer_id or "",
    }


def _is_in_npci_window() -> bool:
    # Check if current IST hour is in non-peak batch window
    now_ist = datetime.now(IST)
    start, end = NPCI_EXECUTION_WINDOW
    return start <= now_ist.hour < end


def execute_case(db: Session, case: Case) -> Action | None:
    # Main loop: choose optimal action and execute via gateway or notification
    case_dict = _case_to_feature_dict(case)
    decision = choose_action(case_dict)
    action_type = decision["action"]

    # 1. Handle hard stop decisions
    if action_type == "stop":
        stop_reason = decision.get("reason", "unknown_stop_reason")
        action_row = Action(
            case_id=case.id,
            action_type="stop",
            reason=stop_reason,
            outcome=stop_reason,
        )
        db.add(action_row)

        if stop_reason == "payment_already_succeeded":
            case.status = "recovered"
        elif stop_reason in ("retry_cap_reached", "hard_decline_no_retry"):
            case.status = "escalated"
        else:
            case.status = "closed"

        db.commit()
        db.refresh(action_row)

        write_audit_log(
            db,
            case_id=case.id,
            description=f"STOP: Case #{case.id} -- action halted",
            reason=f"Stopping condition: {stop_reason}. Case status: {case.status}.",
        )
        logger.info("Case #%d: STOP (%s)", case.id, stop_reason)
        return action_row

    # 2. Defer retries outside the NPCI execution window
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
            description=f"DEFERRED: Case #{case.id} outside NPCI window",
            reason=f"Retry deferred to 12 AM - 7 AM IST window. P(recovery)={decision.get('probability')}.",
        )
        logger.info("Case #%d: retry DEFERRED (IST hour=%d)", case.id, now_ist.hour)
        return action_row

    # 3. Dispatch action
    reasoning = decision.get("reasoning", "")
    probability = decision.get("probability")
    ev = decision.get("expected_value")
    execution_result: dict[str, Any] = {}

    if action_type == "retry":
        sub_id = case_dict.get("razorpay_subscription_id", "")
        execution_result = retry_charge(sub_id)

    elif action_type in ("payment_link_nudge", "whatsapp_nudge"):
        customer_contact = {
            "name": f"Customer {case_dict.get('customer_id', 'Unknown')}",
            "email": "customer@example.com",
            "contact": "",
        }
        execution_result = create_recovery_payment_link(
            amount=float(case.amount or 0),
            customer_contact=customer_contact,
            case_id=str(case.id),
        )

        payment_url = execution_result.get("short_url", "https://rzp.io/rzp/FZeBaY8")
        decline_clean = (case.decline_reason or "expired_card").replace("_", " ")
        msg = f"Namaste! Aapka INR {case.amount:,.0f} ka subscription payment ({decline_clean}) ki wajah se complete nahi ho paya. Kripya is link se update karein: {payment_url}"

        # Dispatch WhatsApp notification if configured
        try:
            from app.notifications.whatsapp import send_whatsapp_recovery_message
            target_phone = str(case.customer_id or "").strip()
            whatsapp_res = send_whatsapp_recovery_message(to_phone=target_phone, message=msg)
            execution_result["whatsapp_dispatch"] = whatsapp_res
        except Exception as e:
            logger.warning("WhatsApp dispatch error: %s", e)

        # Dispatch Email notification if configured
        try:
            from app.notifications.email_service import send_recovery_email
            target_email = str(case.customer_id or "").strip() if "@" in str(case.customer_id or "") else ""
            email_res = send_recovery_email(
                to_email=target_email,
                amount=float(case.amount or 1499.0),
                decline_reason=case.decline_reason or "expired_card",
                payment_url=payment_url,
            )
            execution_result["email_dispatch"] = email_res
        except Exception as e:
            logger.warning("Email dispatch error: %s", e)

    elif action_type == "human_escalation":
        execution_result = escalate_to_human(case_id=str(case.id), reason=reasoning)

    else:
        execution_result = {"outcome": "unknown_action", "action": action_type}

    # 4. Update case status and retry counter
    outcome = execution_result.get("outcome", "unknown")
    if action_type in ("retry", "payment_link_nudge"):
        case.retry_attempt_number = (case.retry_attempt_number or 0) + 1

    if action_type == "human_escalation":
        case.status = "escalated"
    elif case.status == "open":
        case.status = "in_progress"

    # 5. Record action row
    action_row = Action(
        case_id=case.id,
        action_type=action_type,
        reason=reasoning,
        outcome=outcome,
    )
    db.add(action_row)
    db.commit()
    db.refresh(action_row)

    # 6. Seal in hash-chained audit log
    candidates_summary = ""
    all_scored = decision.get("all_candidates_scored")
    if all_scored:
        candidates_summary = "; ".join(f"{c['action']}(EV={c['expected_value']})" for c in all_scored)

    is_simulated = execution_result.get("simulated", False)
    sim_note = " [SIMULATED]" if is_simulated else ""

    write_audit_log(
        db,
        case_id=case.id,
        description=f"EXECUTED{sim_note}: Case #{case.id} -- {action_type} (outcome={outcome})",
        reason=f"P(recovery)={probability}, EV={ev}. Candidates: [{candidates_summary}]. Reasoning: {reasoning}",
    )

    logger.info("Case #%d: %s (outcome=%s, EV=%s, P=%s)%s", case.id, action_type, outcome, ev, probability, sim_note)
    return action_row