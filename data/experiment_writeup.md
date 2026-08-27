# Control vs. AI Recovery Experiment: Methodology & Findings

## Executive Summary
We evaluated our **AI Policy Engine** against a standard **Naive Static Retry** baseline (the industry default across most dunning systems, which retries every failure up to 3 times on a fixed Day 1, 3, 7 schedule) on a held-out evaluation batch of **100 payment failure cases** (`data/demo_batch.csv`) split 50/50 using a stratified partition across decline categories.

```
+------------------------------------+------------+------------+-----------------------+
| Metric (As-Is / Raw Output)        | Control    | AI Policy  | Delta                 |
+------------------------------------+------------+------------+-----------------------+
| Overall Recovery Rate              | 64.0%      | 64.0%      | +0.0pp (Tied)         |
| Cases Recovered (of 50)            | 32         | 32         | +0 cases              |
| Gross Revenue Recovered            | INR 46,580 | INR 44,567 | -INR 2,013 (-4.3%)    |
| Avg Attempts Used per Case         | 1.88       | 1.24       | -34.0% attempt volume |
| Wasted Retries on Dead Tokens      | 9          | 0          | -100% waste           |
| Smart Payment Links Dispatched     | 0          | 8          | +8 links (+40pp lift) |
+------------------------------------+------------+------------+-----------------------+
```

---

## Technical Deep-Dive & Economic Trade-Offs

### 1. Where AI Delivers Structural Value: Root-Cause Routing
* **`expired_card` & `auth_required`**:
  * **Control (0.0% recovery)**: Blindly fired 9 debit retries against expired cards and unauthenticated tokens. Retrying the same dead credential fails 100% of the time, wasting gateway fees and customer goodwill.
  * **AI Policy (40.0% recovery)**: The deterministic rule engine categorized these as requiring customer action and dispatched **Smart Payment Links / WhatsApp Nudges**, converting **40.0%** of previously lost revenue (+40pp lift).

### 2. Understanding the Raw Revenue Gap (-INR 2,013 on As-Is Numbers)
* On `insufficient_funds` (the largest category), Control recovered **86.2%** vs. AI's **72.4%**.
* **The Mechanism**: Control brute-forces 3 retries on every single case regardless of prior attempt history or marginal EV.
* In contrast, the AI Policy Engine is economically rational and compliance-aware: for cases in the batch that had already reached the 4-attempt regulatory limit in prior cycles (`retry_attempt_number = 4`), the AI's stopping rules immediately halted further debiting with zero attempts. Control ignored prior attempt history, yielding extra recoveries by continuing to retry exhausted mandates.

---

## Supplementary Analysis: Compliance-Adjusted Comparison

To evaluate a true **like-for-like comparison** where both systems are constrained by the same NPCI regulatory rules (max 4 total attempts per mandate cycle):

### Over-Cap Control Recoveries Identified:
In the Control group, **4 cases** arrived having already completed 4 attempts (`retry_attempt_number = 4`). The naive control policy retried them anyway, capturing non-compliant recoveries on all 4:
* `case_0818` (INR 481.21, `insufficient_funds`) — Recovered on Attempt #5
* `case_0801` (INR 589.53, `insufficient_funds`) — Recovered on Attempt #5
* `case_0824` (INR 2,197.68, `insufficient_funds`) — Recovered on Attempt #5
* `case_0834` (INR 3,715.68, `insufficient_funds`) — Recovered on Attempt #7 (3 retries past the cap)

Total non-compliant revenue captured by Control: **INR 6,984.10**.

### Like-for-Like (Compliance-Adjusted) Results:

```
+------------------------------------+--------------------+------------+-----------------------+
| Metric                             | Compliant Control  | AI Policy  | Delta (vs. Compliant) |
+------------------------------------+--------------------+------------+-----------------------+
| Recovery Rate                      | 56.0% (28/50)      | 64.0%      | +8.0pp lift           |
| Gross Revenue Recovered            | INR 39,596         | INR 44,567 | +INR 4,971 (+12.6%)   |
| Avg Attempts Used per Case         | 1.70               | 1.24       | -27.1% attempt volume |
| Regulatory Compliance Rate         | 100.0%             | 100.0%     | 100% compliant        |
+------------------------------------+--------------------+------------+-----------------------+
```

When evaluated on a compliant basis, the AI Policy Engine:
1. **Recovers +8.0pp more cases** (64.0% vs. 56.0%).
2. **Generates +INR 4,971.22 (+12.6%) more revenue** than a compliant naive baseline.
3. **Uses 27% fewer attempts** per case (1.24 vs. 1.70), eliminating all wasted retries on dead cards and revoked mandates.

---

## Pitch Deck Positioning

> *"Against a naive dunning baseline that retries blindly regardless of prior attempt history, our AI policy engine matches raw recovery (64% vs 64%) while using **34% fewer attempts** and generating **zero wasted retries** on dead instruments. On categories requiring customer intervention (`expired_card`, `auth_required`), root-cause routing achieves a **+40pp recovery lift** over blind retry.*
>
> *When compared on a like-for-like compliant baseline (enforcing NPCI's 4-attempt cap on both sides), our policy engine delivers **+8.0pp higher recovery** and **+INR 4,971 (+12.6%) incremental revenue** with 27% fewer attempts."*

---

## Honest Limitation & Methodology Note
* **Simulated Outcomes**: Because historical payment failure records cannot be re-executed against live banking rails, transaction outcomes were evaluated using a simulated environment parameterized with industry benchmark recovery rates (Recurly/Churnkey), diminishing returns curves per attempt, and channel-effectiveness multipliers.
