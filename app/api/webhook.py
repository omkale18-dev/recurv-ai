import hashlib
import hmac
import json
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from app.models.db import get_db, Event, Case, write_audit_log

load_dotenv()

router = APIRouter()

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Razorpay's webhook signature using HMAC-SHA256."""
    if not secret:
        return False
    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature or "")


RELEVANT_EVENTS = {
    "payment.failed",
    "subscription.charge.failed",
    "subscription.pending",
    "payment_link.expired",
    "payment_link.paid",
    "payment.captured",
    "order.paid",
}


@router.post("/api/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_signature(raw_body, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    event_id = request.headers.get("X-Razorpay-Event-Id") or payload.get("id")
    event_type = payload.get("event", "unknown")

    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event id")

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
            reason="Not a recovery-relevant event type; ignored.",
        )
        return {"status": "ignored", "reason": "not_relevant"}

    case = handle_event(db, event_type, payload)

    write_audit_log(
        db,
        case_id=case.id if case else None,
        description=f"Processed event {event_type} ({event_id})",
        reason="Recovery-relevant event; case created/updated." if case else "No case action taken.",
    )

    return {"status": "processed", "event_type": event_type}


def handle_event(db: Session, event_type: str, payload: dict):
    entity = payload.get("payload", {})

    if event_type in ("payment.failed", "subscription.charge.failed"):
        payment_entity = entity.get("payment", {}).get("entity", {})
        subscription_entity = entity.get("subscription", {}).get("entity", {})

        payment_id = payment_entity.get("id")
        subscription_id = subscription_entity.get("id")
        amount = (payment_entity.get("amount", 0) or 0) / 100
        decline_reason = payment_entity.get("error_reason") or payment_entity.get("error_description")
        payment_method = payment_entity.get("method")
        customer_id = payment_entity.get("customer_id") or payment_entity.get("contact")

        case = Case(
            razorpay_payment_id=payment_id,
            razorpay_subscription_id=subscription_id,
            customer_id=customer_id,
            amount=amount,
            decline_reason=decline_reason,
            payment_method=payment_method,
            status="open",
            retry_attempt_number=0,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    if event_type in ("payment.captured", "order.paid", "payment_link.paid"):
        payment_entity = entity.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")

        case = None
        if payment_id:
            case = db.query(Case).filter(Case.razorpay_payment_id == payment_id).first()
        if case:
            case.status = "recovered"
            case.recovered_amount = case.amount
            db.commit()
        return case

    if event_type == "payment_link.expired":
        return None

    return None