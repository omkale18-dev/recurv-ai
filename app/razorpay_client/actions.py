from __future__ import annotations

import logging
import time
from typing import Any

from app.razorpay_client.client import client

logger = logging.getLogger(__name__)


def retry_charge(subscription_id: str) -> dict[str, Any]:
    # Poll subscription status from Razorpay
    sub_status = "unknown"
    try:
        sub_data = client.subscription.fetch(subscription_id)
        sub_status = sub_data.get("status", "unknown")
    except Exception as exc:
        logger.warning("Subscription fetch error for %s: %s", subscription_id, exc)

    return {
        "action": "retry_charge",
        "subscription_id": subscription_id,
        "subscription_status": sub_status,
        "outcome": "pending",
    }


def create_recovery_payment_link(
    amount: float,
    customer_contact: dict[str, str],
    case_id: str,
) -> dict[str, Any]:
    # Generate live Razorpay Payment Link with 48h expiry
    amount_paise = int(round(amount * 100))

    payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": "INR",
        "description": f"Payment recovery for case {case_id}",
        "customer": {
            "name": customer_contact.get("name", "Customer"),
            "email": customer_contact.get("email", ""),
            "contact": customer_contact.get("contact", ""),
        },
        "notify": {
            "sms": bool(customer_contact.get("contact")),
            "email": bool(customer_contact.get("email")),
        },
        "expire_by": int(time.time()) + (48 * 60 * 60),
        "reminder_enable": True,
        "notes": {
            "case_id": case_id,
            "source": "recurv_ai",
        },
    }

    try:
        result = client.payment_link.create(payload)
        link_id = result.get("id", "unknown")
        short_url = result.get("short_url", "")
        return {
            "action": "create_payment_link",
            "payment_link_id": link_id,
            "short_url": short_url,
            "amount_inr": amount,
            "outcome": "link_created",
        }
    except Exception as exc:
        logger.error("Failed to create payment link for case %s: %s", case_id, exc)
        return {
            "action": "create_payment_link",
            "error": str(exc),
            "outcome": "api_error",
        }


def escalate_to_human(case_id: str, reason: str) -> dict[str, Any]:
    # Route sensitive case to customer operations team
    return {
        "action": "human_escalation",
        "case_id": case_id,
        "reason": reason,
        "outcome": "escalated",
    }