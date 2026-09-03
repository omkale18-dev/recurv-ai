# Recurv AI
### Autonomous Revenue Recovery for Razorpay Subscriptions & UPI AutoPay

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python)](https://python.org)
[![Razorpay](https://img.shields.io/badge/Razorpay-API%20v2-0C2340.svg?style=flat)](https://razorpay.com)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat)](LICENSE)

---

## 🎥 5-Minute Pitch & Live Demo Video

> 🔗 **Watch Video Submission**: [Add Your YouTube / Loom Link Here](https://youtu.be/your-video-id)

---

## The Problem: India's Involuntary Churn Leak

Subscription businesses in India—from OTT and SaaS to gym memberships and insurance—routinely lose **15% to 30% of recurring revenue** to involuntary churn. This does not happen because customers cancel; it happens when automated card e-mandates or UPI AutoPay debits fail silently in the background.

Most billing setups handle this with dumb cron jobs: retry every 24 hours for 3 days. That causes three big problems:
1. **Wasted Gateway Fees**: Retrying an expired card or dead bank token fails 100% of the time, burning fees on every useless attempt.
2. **NPCI Violations**: Retrying a customer who explicitly revoked their UPI AutoPay mandate violates NPCI guidelines and risks merchant account penalties.
3. **Bad Timing**: If a user runs out of balance on the 28th, dumb systems burn all 3 retry attempts before their salary lands on the 1st.

---

## How Recurv AI Solves It

Recurv AI is an autonomous, root-cause-aware policy engine integrated directly into Razorpay's API and webhooks. Instead of guessing, it makes mathematically grounded decisions for every failed charge.

- **Deterministic Compliance Guardrails**: If a customer revoked their mandate or reached the 4-attempt regulatory limit, the system halts immediately. No AI overrides legal rules.
- **Expected Value (EV) Decision Engine**: Evaluates competing recovery strategies and picks the highest-yield channel:
  $$\text{EV} = (P(\text{recovery}) \times \text{Invoice Amount}) - \text{Action Cost} - \text{Risk Penalty}$$
- **Real Razorpay REST API Execution**: Generates live, dynamic `rzp.io` checkout links with 48-hour expirations and customer notes.
- **Multilingual Messaging**: Drafts contextual, empathetic Hinglish emails and WhatsApp notifications without robotic spam.
- **Cryptographic Audit Trail**: Every webhook, decision, and payment event is chained using SHA-256 hashes (`Hash_n = SHA256(Hash_n-1 + ...)`). If any row in the database is modified, the audit chain breaks visibly.

---

## System Architecture

```
                          [ Razorpay Webhook Event ]
                                       │
                                       ▼ (<50ms)
                     ┌──────────────────────────────────┐
                     │   Idempotent Ingestion Layer     │
                     │   • HMAC-SHA256 verification     │
                     │   • Dedup via razorpay_event_id  │
                     └─────────────────┬────────────────┘
                                       │
                                       ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                           DECISION ENGINE                              │
 │                                                                        │
 │   ┌──────────────────────┐    ┌─────────────────┐    ┌─────────────┐   │
 │   │ 1. Stopping Rules    │───►│ 2. Scikit-Learn │───►│ 3. EV Action│   │
 │   │    (NPCI caps, halts)│    │    Classifier   │    │    Selector │   │
 │   └──────────────────────┘    └─────────────────┘    └─────────────┘   │
 └─────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                           EXECUTION LAYER                              │
 │                                                                        │
 │   • Dynamic Razorpay Payment Link (API generated)                      │
 │   • Non-Peak NPCI Retry Scheduler (12 AM - 7 AM IST batching)          │
 │   • Contextual HTML Email & WhatsApp Dispatch                          │
 │   • Human Escalation for High-Ticket B2B Invoices                      │
 └─────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        AUDIT & OBSERVABILITY                           │
 │                                                                        │
 │   • Tamper-evident SHA-256 hash-chained ledger                         │
 │   • Live SaaS Dashboard (Metrics, Charts, Experiment View)             │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## Real-World Failure Scenarios

| Failure Scenario | Real-World Cause | Dumb System Action | Recurv AI Action |
| :--- | :--- | :--- | :--- |
| **`expired_card`** | Physical card reached MM/YY date. | Retries 3 times (0% success), wastes gateway fees. | Bypasses retries ($P=0$). Creates dynamic Razorpay link and emails customer. |
| **`insufficient_funds`** | Month-end salary delay (28th). | Burns 3 attempts before salary arrives. | Recognizes salary cycle. Schedules silent retry for 1st of month at 6 AM. |
| **`mandate_revoked`** | User cancelled AutoPay in PhonePe/GPay. | Retries anyway, violates NPCI rules. | **Hard Stop (0 retries)**. Halts automation to protect merchant compliance. |
| **`bank_timeout`** | Bank CBS maintenance glitch. | Treats as failure, panics customer. | Classifies as transient. Schedules non-intrusive retry in 4 hours. |
| **High Value (>₹15k)**| Enterprise subscription failure. | Sends link with high drop-off rate. | Routes to human account manager with pre-built recovery dossier. |

---

## Benchmark Results (100-Case Held-Out Test)

We ran a controlled experiment comparing a standard Naive Retry strategy (3 retries on fixed intervals) against Recurv AI across a held-out dataset of 100 failed transactions:

| Metric | Naive Control | Recurv AI | Impact |
| :--- | :---: | :---: | :---: |
| **Overall Recovery Rate** | 45.0% | **85.0%** | **+40.0% lift** |
| **Wasted Retries on Dead Cards** | 48 attempts | **0 attempts** | **-100% waste** |
| **Average Attempts per Case** | 2.85 | **1.88** | **-34.0% lower** |
| **Net Recovered Amount** | ₹58,400 | **₹1,12,300** | **+92.3% revenue** |
| **NPCI Compliance Violations** | 14 cases | **0 cases** | **100% compliant** |

---

## Quickstart Guide

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/omkale18-dev/revenue-recovery-agent.git
cd revenue-recovery-agent

python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the template file:
```bash
cp .env.example .env
```
Fill in your credentials:
```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...

# Optional: Email Notifications (Gmail SMTP App Password)
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_16_digit_app_password
```

### 3. Run the App
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at:
👉 **`http://127.0.0.1:8000/dashboard`**

---

## Running the Benchmark & Tests

```bash
# Run unit tests
pytest app/policy/test_decision_engine.py -v

# Run the 100-case comparison benchmark
python scripts/run_experiment.py

# Simulate a live webhook event with HMAC signature
python scripts/simulate_payment_recovery.py --event payment.failed --reason expired_card --amount 1499.0
```

---

## Repository Structure

```
revenue-recovery-agent/
├── app/
│   ├── api/
│   │   ├── dashboard.py          # Dashboard endpoints & metrics
│   │   └── webhook.py            # HMAC-verified webhook ingestion
│   ├── ml/
│   │   ├── features.py           # Feature engineering pipeline
│   │   ├── llm_tasks.py          # Gemini promise-to-pay extraction
│   │   ├── predict.py            # Inference module
│   │   └── train.py              # Scikit-learn model training
│   ├── models/
│   │   └── db.py                 # SQLAlchemy schemas & SHA-256 hash chaining
│   ├── notifications/
│   │   ├── email_service.py      # Responsive HTML email recovery dispatcher
│   │   └── whatsapp.py           # WhatsApp recovery notification worker
│   ├── policy/
│   │   ├── constants.py          # NPCI caps, execution windows, and costs
│   │   ├── decision_engine.py    # Expected Value (EV) decision logic
│   │   ├── executor.py           # Action orchestrator & state updater
│   │   └── rules.py              # Deterministic compliance stopping rules
│   ├── static/                   # Assets and logos
│   └── templates/
│       └── dashboard.html        # Production dashboard UI
├── data/                         # Benchmark datasets & artifacts
├── scripts/                      # Testing, simulation, and benchmark scripts
├── main.py                       # FastAPI entrypoint
└── requirements.txt              # Dependencies
```

---

## Security & Compliance
- **HMAC-SHA256 Webhook Verification**: All requests to `/api/razorpay/webhook` validate the `X-Razorpay-Signature` header.
- **Zero Raw Card Storage**: No payment card numbers or CVVs ever touch our application database. All actions operate via Razorpay tokens and short URLs.
- **Idempotency**: Webhook events are deduplicated by `razorpay_event_id` in database transactions to prevent double charges.
- **Tamper Evidence**: Cryptographic hash chaining ensures all state changes can be independently audited.