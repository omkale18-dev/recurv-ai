"""
Simulate a live Razorpay payment webhook (payment.failed / payment.captured)
with authentic HMAC-SHA256 signature verification.

Demonstrates end-to-end live flow for judges:
1. Dispatches authentic HMAC-SHA256 signed HTTP POST webhook to /api/razorpay/webhook
2. Server validates cryptographic signature
3. Ingests case, executes ML Expected Value decision, generates live link & drafts message
4. Updates tamper-evident SHA-256 Audit Log
5. Dashboard metrics update live!
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = "http://127.0.0.1:8000/api/razorpay/webhook"
WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

if not WEBHOOK_SECRET:
    print("[ERROR] RAZORPAY_WEBHOOK_SECRET not set in .env")
    sys.exit(1)


def dispatch(event_type="payment.failed", decline_reason="expired_card", amount=1499.0, case_id=None):
    timestamp = int(time.time())
    event_id = f"evt_live_{event_type.replace('.', '_')}_{timestamp}"
    payment_id = f"pay_live_{timestamp}"
    sub_id = f"sub_live_{timestamp}"

    desc_map = {
        "expired_card": "Card has expired",
        "insufficient_funds": "Customer account balance low",
        "mandate_revoked": "Customer cancelled UPI AutoPay mandate",
        "bank_timeout": "Issuer bank network timed out",
        "auth_required": "3DS / OTP Authentication required",
    }
    error_desc = desc_map.get(decline_reason, "Payment authorization failed")

    if event_type == "payment.failed":
        payload = {
            "entity": "event",
            "account_id": "acc_demo_live",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "entity": "payment",
                        "amount": int(round(amount * 100)),
                        "currency": "INR",
                        "status": "failed",
                        "method": "upi" if "mandate" in decline_reason else "card",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": error_desc,
                        "error_reason": decline_reason,
                        "customer_id": "cust_live_demo",
                    }
                },
                "subscription": {
                    "entity": {
                        "id": sub_id,
                        "customer_id": "cust_live_demo",
                    }
                }
            },
            "created_at": timestamp
        }
    else:  # payment.captured
        payload = {
            "entity": "event",
            "account_id": "acc_demo_live",
            "event": "payment.captured",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "entity": "payment",
                        "amount": int(round(amount * 100)),
                        "currency": "INR",
                        "status": "captured",
                        "order_id": f"order_rec_{timestamp}",
                        "method": "upi",
                        "description": f"Recovery for case {case_id or 'latest'}",
                        "notes": {
                            "case_id": str(case_id) if case_id else "",
                            "source": "revenue_recovery_agent"
                        }
                    }
                }
            },
            "created_at": timestamp
        }

    body_bytes = json.dumps(payload).encode("utf-8")

    # Generate authentic HMAC-SHA256 signature
    signature = hmac.new(
        key=WEBHOOK_SECRET.encode("utf-8"),
        msg=body_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()

    print("\n" + "=" * 70)
    print(f"  [DISPATCHING LIVE WEBHOOK] -> {event_type}")
    print("=" * 70)
    print(f"Target URL           : {SERVER_URL}")
    print(f"Event ID             : {event_id}")
    print(f"Amount               : INR {amount:,.2f} ({int(round(amount * 100))} paise)")
    if event_type == "payment.failed":
        print(f"Decline Reason       : {decline_reason} ({error_desc})")
    print(f"X-Razorpay-Signature : {signature[:24]}... (HMAC-SHA256)")
    print("-" * 70)
    print("Sending authenticated HTTP POST request to server...")

    req = urllib.request.Request(
        SERVER_URL,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
            "User-Agent": "Razorpay-Webhook/v1",
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode())
            print(f"[SUCCESS] HTTP {resp.status} OK")
            print(f"Server Response      : {json.dumps(resp_data, indent=2)}")
            print("-" * 70)
            if event_type == "payment.failed":
                print(f"[ACTION] Case #{resp_data.get('case_id')} opened! Refresh dashboard to see live status.")
            else:
                print(f"[RECOVERED] Case #{resp_data.get('case_id')} marked RECOVERED (+INR {amount:,.0f})!")
            print("=" * 70 + "\n")
    except Exception as e:
        print(f"[FAILED] Webhook dispatch error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dispatch authentic Razorpay webhook for live judge demo")
    parser.add_argument("--event", choices=["payment.failed", "payment.captured"], default="payment.failed", help="Event type")
    parser.add_argument("--reason", default="expired_card", choices=["expired_card", "insufficient_funds", "mandate_revoked", "bank_timeout"], help="Decline reason")
    parser.add_argument("--amount", type=float, default=1499.0, help="Amount in INR")
    parser.add_argument("--case_id", type=str, default=None, help="Case ID to recover")

    args = parser.parse_args()
    dispatch(event_type=args.event, decline_reason=args.reason, amount=args.amount, case_id=args.case_id)

