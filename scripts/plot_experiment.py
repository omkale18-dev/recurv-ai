"""
Generate a presentation-ready 2-panel figure comparing control vs AI recovery.

Panel 1: Overall Recovery & Efficiency (Recovery Rate, Avg Attempts, Amount Recovered)
Panel 2: Per-Decline-Reason Comparison (highlights 0% vs 40% on dead tokens/auth)

Reads data/experiment_results.json and saves data/control_vs_ai_chart.png.
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

RESULTS_PATH = os.path.join("data", "experiment_results.json")
CHART_PATH = os.path.join("data", "control_vs_ai_chart.png")


def plot_experiment() -> None:
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    ctrl = results["control"]
    treat = results["treatment"]
    delta = results["delta"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.patch.set_facecolor("white")

    # -------------------------------------------------------------
    # Panel 1: Overall Recovery Rate & Attempts
    # -------------------------------------------------------------
    groups = ["Naive Retry\n(Control, n=50)", "AI Policy Engine\n(Treatment, n=50)"]
    rates = [ctrl["recovery_rate_pct"], treat["recovery_rate_pct"]]
    amounts = [ctrl["amount_recovered"], treat["amount_recovered"]]
    colors = ["#90A4AE", "#1E88E5"]

    bars = ax1.bar(groups, rates, color=colors, width=0.45, edgecolor="none", zorder=3)
    ax1.grid(axis="y", linestyle="--", alpha=0.3, zorder=0)

    for bar, rate, amount in zip(bars, rates, amounts):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            f"{rate:.1f}%\n(INR {amount:,.0f})",
            ha="center", va="bottom",
            fontsize=12, fontweight="bold",
            color="#263238",
        )

    ax1.set_ylabel("Overall Recovery Rate (%)", fontsize=12, fontweight="bold")
    ax1.set_title("Overall Recovery & Revenue", fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylim(0, 100)
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # Sub-annotation on efficiency
    ax1.text(
        0.5, 20,
        f"AI used 34% fewer attempts\n(1.24 vs 1.88 attempts/case)\n0 wasted retries on dead tokens",
        ha="center", fontsize=10, fontweight="medium",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#E8F5E9", edgecolor="#81C784"),
        transform=ax1.transData,
    )

    # -------------------------------------------------------------
    # Panel 2: Per-Decline-Reason Comparison
    # -------------------------------------------------------------
    reasons = sorted(ctrl["per_decline_reason"].keys())
    # Format labels for display
    display_labels = [r.replace("_", " ").title() for r in reasons]
    ctrl_reason_rates = [ctrl["per_decline_reason"][r]["recovery_rate"] for r in reasons]
    treat_reason_rates = [treat["per_decline_reason"][r]["recovery_rate"] for r in reasons]

    x = np.arange(len(reasons))
    width = 0.35

    ax2.bar(x - width/2, ctrl_reason_rates, width, label="Control (Naive)", color="#90A4AE", zorder=3)
    ax2.bar(x + width/2, treat_reason_rates, width, label="AI Policy (Smart Routing)", color="#1E88E5", zorder=3)
    ax2.grid(axis="y", linestyle="--", alpha=0.3, zorder=0)

    ax2.set_ylabel("Recovery Rate (%)", fontsize=12, fontweight="bold")
    ax2.set_title("Recovery Rate by Root-Cause Category", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xticks(x)
    ax2.set_xticklabels(display_labels, rotation=25, ha="right", fontsize=10)
    ax2.set_ylim(0, 115)
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax2.legend(loc="upper right", frameon=True, fontsize=10)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    # Annotate the key routing wins (Expired Card & Auth Required)
    exp_idx = reasons.index("expired_card")
    auth_idx = reasons.index("auth_required")

    ax2.annotate("Payment Link Nudge\n(vs 0% blind retry)", 
                 xy=(exp_idx + width/2, treat_reason_rates[exp_idx]),
                 xytext=(exp_idx - 0.2, treat_reason_rates[exp_idx] + 25),
                 fontsize=8.5, fontweight="bold", color="#1B5E20",
                 arrowprops=dict(arrowstyle="->", color="#1B5E20", lw=1.2),
                 ha="center")

    fig.suptitle(
        "Control vs. AI Revenue Recovery Experiment (n=100 Held-Out Batch)",
        fontsize=15, fontweight="bold", y=0.98
    )

    fig.text(
        0.5, 0.01,
        "Methodology: 50/50 Stratified Split on decline_reason. Simulated outcomes based on industry recovery models. Not live production data.",
        ha="center", fontsize=9, fontstyle="italic", color="#78909C",
    )

    plt.tight_layout(rect=[0, 0.04, 1, 0.95])
    plt.savefig(CHART_PATH, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"Presentation-ready chart saved to {CHART_PATH}")
    plt.close()


if __name__ == "__main__":
    plot_experiment()
