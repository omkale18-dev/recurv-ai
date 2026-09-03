from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
_MODEL = "gemini-3.6-flash"


def _get_client() -> genai.Client:
    # Initialize cached Gemini API client
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


def _call_llm(prompt: str, max_retries: int = 2) -> str:
    # Call Gemini model with automatic retry
    client = _get_client()
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=_MODEL,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as exc:
            logger.warning("LLM invocation error (attempt %d/%d): %s", attempt + 1, max_retries + 1, exc)
            if attempt == max_retries:
                raise
    return ""


_PROMISE_SYSTEM_PROMPT = """You are a payment recovery assistant analyzing customer messages.
Extract structured information from customer message. Today: {today}, Due: INR {amount}.
Return ONLY valid JSON:
{{
  "promise_date": "YYYY-MM-DD" or null,
  "promise_amount": float or null,
  "confidence": 0.0 to 1.0,
  "detected_opt_out": boolean,
  "already_paid_claim": boolean,
  "summary": "one sentence summary"
}}
"""


def extract_promise_to_pay(
    customer_message: str,
    case_context: dict[str, Any],
) -> dict[str, Any] | None:
    # Parse structured promise dates and intents from free-text customer replies
    today = case_context.get("today", datetime.now().strftime("%Y-%m-%d"))
    amount = case_context.get("amount", 0.0)

    prompt = _PROMISE_SYSTEM_PROMPT.format(today=today, amount=amount)
    prompt += f"\n\nCustomer message:\n\"{customer_message}\"\n\nJSON output:"

    try:
        raw = _call_llm(prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        result["promise_date"] = result.get("promise_date") or None
        result["promise_amount"] = float(result["promise_amount"]) if result.get("promise_amount") is not None else None
        result["confidence"] = float(result.get("confidence", 0.0))
        result["detected_opt_out"] = bool(result.get("detected_opt_out", False))
        result["already_paid_claim"] = bool(result.get("already_paid_claim", False))
        result.setdefault("summary", "")
        return result
    except Exception as exc:
        logger.error("Promise extraction failed: %s", exc)
        return None


_MESSAGE_SYSTEM_PROMPT = """Draft a short, polite recovery nudge (2-3 sentences) in {language}.
Reason: {decline_reason}, Amount: INR {amount}, Method: {payment_method}.
Keep tone empathetic and non-coercive. Return message text only."""


def draft_recovery_message(
    case: dict[str, Any],
    language: str = "hinglish",
) -> str:
    # Draft contextual, localized notification copy
    prompt = _MESSAGE_SYSTEM_PROMPT.format(
        decline_reason=case.get("decline_reason", "unknown"),
        amount=case.get("amount", 0),
        payment_method=case.get("payment_method", "unknown"),
        language=language,
    )

    try:
        message = _call_llm(prompt)
        if message.startswith('"') and message.endswith('"'):
            message = message[1:-1]
        return message
    except Exception as exc:
        logger.error("Message drafting fallback: %s", exc)
        return f"Hi, your payment of INR {case.get('amount', 0):.0f} could not be processed. Please use the secure link sent to complete it at your convenience. Thank you!"