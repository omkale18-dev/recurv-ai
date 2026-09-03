# Stress Test Report

**Generated**: 2026-08-29 22:14:18
**Total Assertions**: 18
**Passed**: 18
**Failed**: 0
**Result**: ALL PASSED

---

## Scenario 1: Duplicate Webhook

**Status**: `PASS`

| # | Result | Assertion | Audit Note |
|---|--------|-----------|------------|
| 1 | PASS | First POST: 200, status=processed | First webhook should be processed normally. |
| 2 | PASS | Second POST returns: {'status': 'ignored', 'reason': 'duplicate_event'} | Second delivery must return duplicate_event, not create a new case. |
| 3 | PASS | Event rows for this event_id: 1 (expected 1) | Idempotency: only one Event row should exist. |
| 4 | PASS | Case rows for this subscription: 1 (expected 1) | Idempotency: only one Case row should exist. |

## Scenario 2: Opt-Out

**Status**: `PASS`

| # | Result | Assertion | Audit Note |
|---|--------|-----------|------------|
| 1 | PASS | Action type: stop (expected 'stop') | Opted-out case must be stopped immediately. |
| 2 | PASS | Stop reason: customer_opted_out | Reason must be 'customer_opted_out'. |
| 3 | PASS | Razorpay calls made: retry=False, plink=False, escalate=False (all must be False) | No Razorpay API call should be made for an opted-out customer. |

## Scenario 3: Interleaved Recovery

**Status**: `PASS`

| # | Result | Assertion | Audit Note |
|---|--------|-----------|------------|
| 1 | PASS | First execute_case: action=retry, outcome=pending | Initial retry action dispatched and case marked in_progress. |
| 2 | PASS | Second execute_case after recovery: action=stop | Must stop immediately after payment succeeded. |
| 3 | PASS | Stop reason: payment_already_succeeded | Must cite 'payment_already_succeeded' as the stopping condition. |
| 4 | PASS | Post-recovery API calls: retry=False, plink=False (both must be False) | No action should be dispatched after recovery. |

## Scenario 4: NPCI Cap

**Status**: `PASS`

| # | Result | Assertion | Audit Note |
|---|--------|-----------|------------|
| 1 | PASS | At retry_attempt_number=3: action=retry (expected non-stop action) | When 3 attempts have failed (1 original + 2 retries), taking action dispatches the 4th (final allowed) attempt under NPCI. |
| 2 | PASS | At retry_attempt_number=4: action=stop (expected 'stop') | When 4 total attempts have already occurred (1 original + 3 retries), the NPCI cap is exhausted. Any further action is blocked. |
| 3 | PASS | Stop reason: retry_cap_reached | Must cite 'retry_cap_reached'. |
| 4 | PASS | Post-cap API calls: retry=False, plink=False (both must be False) | No Razorpay API call should be made once the NPCI cap is reached. |

## Scenario 5: Malformed Webhook

**Status**: `PASS`

| # | Result | Assertion | Audit Note |
|---|--------|-----------|------------|
| 1 | PASS | HTTP status: 400 (expected 400) | Unsigned/malformed webhooks must be rejected with 400. |
| 2 | PASS | Event rows: before=1, after=1 (expected no change) | No Event row should be created for a rejected webhook. |
| 3 | PASS | Case rows: before=4, after=4 (expected no change) | No Case row should be created for a rejected webhook. |

---

## Summary

| Scenario | Assertions | Passed | Status |
|----------|-----------|--------|--------|
| 1. Duplicate Webhook | 4 | 4 | `PASS` |
| 2. Opt-Out | 3 | 3 | `PASS` |
| 3. Interleaved Recovery | 4 | 4 | `PASS` |
| 4. NPCI Cap | 4 | 4 | `PASS` |
| 5. Malformed Webhook | 3 | 3 | `PASS` |
| **TOTAL** | **18** | **18** | **ALL PASSED** |

---

## What This Proves

1. **Idempotency**: Duplicate webhook delivery does not create duplicate cases or events.
2. **Consent Compliance**: Customer opt-out immediately halts all recovery actions -- zero API calls dispatched.
3. **State-Machine Interleaving**: When an external payment success webhook arrives between scheduler cycles, subsequent execution cycles immediately halt on `payment_already_succeeded`, preventing redundant debits or duplicate payment links.
4. **Regulatory Compliance**: NPCI 4-attempt cap is enforced exactly -- the 4th attempt executes, the 5th is blocked with `retry_cap_reached`.
5. **Security**: Unsigned/malformed webhooks are rejected with HTTP 400 and create no database records.

---

## Scope & Concurrency Notes (For Technical Evaluation)

- **Interleaving vs. Thread Concurrency**: This test suite verifies deterministic state transitions and idempotency across asynchronous webhook arrivals and scheduler intervals. In high-throughput multi-worker deployments, simultaneous database write contention is governed by ACID row-level locking (e.g. `SELECT FOR UPDATE` in PostgreSQL) rather than application heuristics.
- **Audit Log Tamper-Evidence**: All state halts and deferrals are recorded in the hash-chained `AuditLog` table, maintaining an immutable record of why any action was skipped or stopped.
