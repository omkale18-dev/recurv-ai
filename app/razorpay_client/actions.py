"""
Razorpay API action wrappers for the Revenue Recovery Agent.

Each function in this module maps to a specific recovery action that the
decision engine may choose. Functions call the Razorpay test-mode SDK where
a real API endpoint exists, and clearly mark simulated operations where the
SDK does not expose the needed functionality.

Honesty policy: every function's docstring states whether it makes a REAL
API call or a SIMULATED one, and why.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.razorpay_client.client import client

logger = logging.getLogger(__name__)


def retry_charge(subscription_id: str) -> dict[str, Any]:
    """Attempt to retry a failed subscription charge.

    SIMULATED -- NOT a real API call.

    The Razorpay SDK (v2.0.1) does not expose a method to manually trigger
    a subscription charge retry. In production, NPCI mandate retries are
    initiated automatically by Razorpay's internal scheduler according to
    the mandate's retry configuration. The merchant cannot programmatically
    force a retry via the API.

    The closest SDK methods are:
      - subscription.fetch(id)  -- read-only status check
      - subscription.pending_update(id) -- check pending changes
      - subscription.resume(id) -- resume a paused subscription (different)

    None of these trigger a charge retry on a failed/pending subscription.

    For the hackathon demo, this function SIMULATES a retry by:
      1. Fetching the subscription to confirm it exists (REAL API call)
      2. Returning a simulated success/failure result (NOT a real charge)
      3. Logging clearly that this is simulated

    In a production deployment, the retry would be triggered by Razorpay's
    own scheduler, and our system would observe the result via the
    subscription.charged or subscription.pending webhook.
    """
    logger.info(
        "[SIMULATED RETRY] Subscription %s -- Razorpay SDK does not expose "
        "manual retry triggering. Fetching subscription status instead.",
        subscription_id,
    )

    # REAL API call: fetch subscription to confirm it exists and get status
    try:
        sub_data = client.subscription.fetch(subscription_id)
        sub_status = sub_data.get("status", "unknown")
        logger.info(
            "[REAL API] Fetched subscription %s, status=%s",
            subscription_id, sub_status,
        )
    except Exception as exc:
        logger.warning(
            "[REAL API] Failed to fetch subscription %s: %s. "
            "Proceeding with simulated retry result.",
            subscription_id, exc,
        )
        sub_data = {}
        sub_status = "unknown"

    # SIMULATED result -- in production this would come from a webhook
    return {
        "action": "retry_charge",
        "simulated": True,
        "simulation_note": (
            "Razorpay does not expose manual retry triggering via SDK. "
            "In production, retries are scheduled by Razorpay internally "
            "and results arrive via subscription.charged/subscription.pending "
            "webhooks. This result is simulated for demo purposes."
        ),
        "subscription_id": subscription_id,
        "subscription_status": sub_status,
        "outcome": "pending",  # We don't know the result yet -- it would come via webhook
    }


def create_recovery_payment_link(
    amount: float,
    customer_contact: dict[str, str],
    case_id: str,
) -> dict[str, Any]:
    """Create a Razorpay Payment Link for recovering a failed payment.

    REAL API call -- Payment Links API is fully available in Razorpay test mode.

    Creates a short-lived payment link (48h expiry) with SMS/email
    notifications enabled, referencing the recovery case ID in the
    description for traceability.

    Parameters
    ----------
    amount : float
        Amount in INR to recover.
    customer_contact : dict
        Must contain at least "name" and one of "email" or "contact" (phone).
    case_id : str
        The internal case ID, included in the link description for audit trail.
    """
    # Razorpay expects amount in paise (1 INR = 100 paise)
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
        # 48-hour expiry from now
        "expire_by": int(time.time()) + (48 * 60 * 60),
        "reminder_enable": True,
        "notes": {
            "case_id": case_id,
            "source": "revenue_recovery_agent",
        },
    }

    logger.info(
        "[REAL API] Creating payment link for case %s, amount=%.2f INR",
        case_id, amount,
    )

    try:
        result = client.payment_link.create(payload)
        link_id = result.get("id", "unknown")
        short_url = result.get("short_url", "")
        logger.info(
            "[REAL API] Payment link created: id=%s, url=%s",
            link_id, short_url,
        )
        return {
            "action": "create_payment_link",
            "simulated": False,
            "payment_link_id": link_id,
            "short_url": short_url,
            "amount_inr": amount,
            "outcome": "link_created",
        }
    except Exception as exc:
        logger.error(
            "[REAL API] Failed to create payment link for case %s: %s",
            case_id, exc,
        )
        return {
            "action": "create_payment_link",
            "simulated": False,
            "error": str(exc),
            "outcome": "api_error",
        }


def escalate_to_human(case_id: str, reason: str) -> dict[str, Any]:
    """Mark a case for manual human review.

    NOT an external API call -- this is an internal routing decision.
    The case is flagged for a CS agent to review via non-automated channels
    (phone call, manual email, etc.).

    In a production system this would integrate with a ticketing system
    (Zendesk, Freshdesk, internal CRM). For the hackathon demo, it returns
    a structured result that the executor writes to the DB.
    """
    logger.info(
        "[INTERNAL] Escalating case %s to human review. Reason: %s",
        case_id, reason,
    )
    return {
        "action": "human_escalation",
        "simulated": False,  # This IS the real action -- there's no API to call
        "case_id": case_id,
        "reason": reason,
        "outcome": "escalated",
        "note": (
            "Case routed to manual review. In production, this would create "
            "a ticket in the CS queue."
        ),
    }
