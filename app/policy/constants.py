# Compliance and policy constants

# NPCI mandate max attempts: 1 original + 3 retries
NPCI_MAX_TOTAL_ATTEMPTS: int = 4

# NPCI non-peak batch processing window in IST (12 AM to 7 AM)
NPCI_EXECUTION_WINDOW: tuple[int, int] = (0, 7)

# Marginal action cost in INR
ACTION_COSTS: dict[str, float] = {
    "retry": 0.0,
    "payment_link_nudge": 2.0,
    "whatsapp_nudge": 5.0,
    "human_escalation": 150.0,
}

# Risk penalty by decline reason in INR
RISK_PENALTIES: dict[str, float] = {
    "mandate_revoked": 500.0,
    "auth_required": 50.0,
    "expired_card": 10.0,
    "insufficient_funds": 5.0,
    "bank_timeout": 0.0,
    "generic_decline": 10.0,
}