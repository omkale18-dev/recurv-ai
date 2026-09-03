import hashlib
import hmac
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.models.db import get_db, Event, Case, write_audit_log

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    # Verify HMAC-SHA256 signature from Razorpay
    if not secret:
        return False
    expected = hmac.new(key=secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


RELEVANT_EVENTS = {
    "payment.failed",
    "payment.captured",
    "order.paid",
    "payment_link.paid",
    "payment_link.expired",
    "payment_link.cancelled",
    "subscription.pending",
    "subscription.charged",
    "subscription.halted",
    "subscription.activated",
    "subscription.cancelled",
}


@router.post("/api/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # 1. Signature verification
    if not verify_signature(raw_body, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    event_id = request.headers.get("X-Razorpay-Event-Id") or payload.get("id")
    event_type = payload.get("event", "unknown")

    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event id")

    # 2. Idempotency check: ignore duplicate deliveries
    existing = db.query(Event).filter(Event.razorpay_event_id == event_id).first()
    if existing:
        return {"status": "ignored", "reason": "duplicate_event"}

    event_row = Event(
        razorpay_event_id=event_id,
        event_type=event_type,
        payload_json=raw_body.decode("utf-8"),
    )
    db.add(event_row)
    db.commit()
    db.refresh(event_row)

    if event_type not in RELEVANT_EVENTS:
        write_audit_log(
            db,
            case_id=None,
            description=f"Received event {event_type} ({event_id})",
            reason="Non-recovery event ignored.",
        )
        return {"status": "ignored", "reason": "not_relevant"}

    case = handle_event(db, event_type, payload)

    # 3. Trigger recovery executor immediately on failure
    if case and event_type in ("payment.failed", "subscription.pending"):
        from app.policy.executor import execute_case
        try:
            execute_case(db, case)
        except Exception as ex:
            logger.error("Auto-execution failed for case #%d: %s", case.id, ex)

    write_audit_log(
        db,
        case_id=case.id if case else None,
        description=f"Processed event {event_type} ({event_id})",
        reason="Recovery-relevant event processed." if case else "No case action taken.",
    )

    return {
        "status": "processed",
        "event_type": event_type,
        "case_id": case.id if case else None,
    }


def handle_event(db: Session, event_type: str, payload: dict):
    # Ingest event and update or create case record
    entity = payload.get("payload", {})

    if event_type in ("payment.failed", "subscription.pending"):
        payment_entity = entity.get("payment", {}).get("entity", {})
        subscription_entity = entity.get("subscription", {}).get("entity", {})

        payment_id = payment_entity.get("id")
        subscription_id = subscription_entity.get("id")

        amount_paise = payment_entity.get("amount")
        if amount_paise is None and subscription_entity:
            amount_paise = subscription_entity.get("plan", {}).get("item", {}).get("amount", 0)
        amount = (amount_paise or 0) / 100

        raw_reason = str(
            payment_entity.get("error_reason")
            or payment_entity.get("error_description")
            or "expired_card"
        ).lower()

        # Normalize gateway error code to canonical categories
        if any(w in raw_reason for w in ("international", "expired", "token", "card_expired", "invalid_card")):
            decline_reason = "expired_card"
        elif any(w in raw_reason for w in ("balance", "fund", "insufficient", "limit")):
            decline_reason = "insufficient_funds"
        elif any(w in raw_reason for w in ("mandate", "cancel", "revoke", "paused")):
            decline_reason = "mandate_revoked"
        elif any(w in raw_reason for w in ("timeout", "network", "down", "unavailable")):
            decline_reason = "bank_timeout"
        else:
            decline_reason = raw_reason

        payment_method = payment_entity.get("method") or "upi"
        customer_id = (
            payment_entity.get("email")
            or payment_entity.get("contact")
            or payment_entity.get("customer_id")
            or subscription_entity.get("customer_id")
            or f"cust_{payment_id or 'unknown'}"
        )

        case = Case(
            razorpay_payment_id=payment_id,
            razorpay_subscription_id=subscription_id,
            customer_id=customer_id,
            amount=amount,
            decline_reason=decline_reason,
            payment_method=payment_method,
            status="open",
            retry_attempt_number=1,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    if event_type in ("payment.captured", "order.paid", "payment_link.paid", "subscription.charged"):
        payment_entity = entity.get("payment", {}).get("entity", {})
        subscription_entity = entity.get("subscription", {}).get("entity", {})
        plink_entity = entity.get("payment_link", {}).get("entity", {})

        payment_id = payment_entity.get("id")
        subscription_id = subscription_entity.get("id")
        notes = plink_entity.get("notes", {}) or payment_entity.get("notes", {})
        note_case_id = notes.get("case_id")

        case = None
        if note_case_id:
            try:
                case = db.query(Case).filter(Case.id == int(note_case_id)).first()
            except (ValueError, TypeError):
                pass
        if not case and subscription_id:
            case = db.query(Case).filter(Case.razorpay_subscription_id == subscription_id).order_by(Case.id.desc()).first()
        if not case and payment_id:
            case = db.query(Case).filter(Case.razorpay_payment_id == payment_id).order_by(Case.id.desc()).first()
        if not case:
            case = db.query(Case).filter(Case.status.in_(["open", "in_progress"])).order_by(Case.id.desc()).first()

        if case:
            case.status = "recovered"
            case.recovered_amount = case.amount
            db.commit()
        return case

    if event_type == "subscription.halted":
        subscription_entity = entity.get("subscription", {}).get("entity", {})
        subscription_id = subscription_entity.get("id")
        case = None
        if subscription_id:
            case = db.query(Case).filter(Case.razorpay_subscription_id == subscription_id).order_by(Case.id.desc()).first()
        if case:
            case.status = "escalated"
            db.commit()
        return case

    if event_type in ("subscription.cancelled", "payment_link.cancelled"):
        subscription_entity = entity.get("subscription", {}).get("entity", {})
        subscription_id = subscription_entity.get("id")
        case = None
        if subscription_id:
            case = db.query(Case).filter(Case.razorpay_subscription_id == subscription_id).order_by(Case.id.desc()).first()
        if case:
            case.status = "closed"
            db.commit()
        return case

    return None