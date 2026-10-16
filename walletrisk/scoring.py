"""Risk scoring — concentration, approvals, dormancy, per the product spec.
Scores are informational, not financial advice."""

from __future__ import annotations

import math


def concentration_score(total_usd: float, assets: list[dict]) -> tuple[int, list[dict]]:
    """HHI-based concentration: 1 - sum(w_i^2) scaled to 0-100 (higher = more
    concentrated = riskier). Weights include native balance as an asset."""
    if total_usd <= 0 or not assets:
        return 0, []
    weights = []
    for a in assets:
        usd = a.get("usd", 0) or 0
        w = usd / total_usd
        if w > 0:
            weights.append((a, w))
    hhi = sum(w * w for _, w in weights)
    # HHI on weights: 1.0 = everything in one asset -> 100
    score = round(100 * hhi)
    return max(0, min(100, score)), [dict(a, weight=w) for a, w in weights]


def approval_score(live_approvals: list[dict]) -> tuple[int, list[dict]]:
    """Risk from live ERC-20 approvals: unlimited approvals weigh most, and
    approvals on risky spenders more still. usd_value_at_risk is approximate
    (current wallet balance can't be at risk — it's at the SPENDER's mercy).

    2026-10-16: actively-exposed unlimited approvals now add a +15 floor
    per finding — an unlimited allowance on a token you still hold is the
    classic rug vector and must never grade below C (composite weights
    otherwise dilute it into 'low risk' territory)."""
    score = 0
    notes: list[dict] = []
    unlimited = [a for a in live_approvals if a.get("unlimited")]
    scored = [a for a in live_approvals if not a.get("unlimited")]
    for a in unlimited:
        # unlimited approvals are the classic rug vector
        base = 6 if not a.get("usd_value_at_risk") else min(25, 6 + math.log10(
            max(10, a["usd_value_at_risk"])) * 4)
        if a.get("usd_value_at_risk"):
            base = max(base, 21)  # actively exposed unlimited: >= 21
        score += base
    for a in scored:
        score += 2 if not a.get("usd_value_at_risk") else min(10, 2 + math.log10(
            max(10, a["usd_value_at_risk"])) * 2)
    return max(0, min(100, round(score))), unlimited


def dormancy_score(days_idle: float | None, tx_count: int) -> tuple[int, str]:
    """Long-idle wallets are phish-revival / dust-reuse targets, and stale
    approvals stay live forever. Active wallets score low."""
    if days_idle is None:
        return 15, "no on-chain activity found"
    if days_idle < 7:
        base = 5
    elif days_idle < 30:
        base = 8
    elif days_idle < 90:
        base = 18
    elif days_idle < 365:
        base = 30
    else:
        base = 45
    if tx_count < 10:
        base += 5  # low-history wallets: approvals unknown, dust-prone
    return max(0, min(100, base)), f"idle {days_idle:.0f}d, {tx_count} txs"


def composite(scores: dict[str, int]) -> int:
    """Weighted blend. Weights are product decisions, not financial advice:
    approvals (live exploitability) > concentration (loss magnitude) > dormancy
    (contextual)."""
    w = {"approvals": 0.45, "concentration": 0.35, "dormancy": 0.20}
    total = 0
    for k, weight in w.items():
        total += scores.get(k, 0) * weight
    return max(0, min(100, round(total)))


def grade(score: int) -> str:
    if score < 20:
        return "A"
    if score < 40:
        return "B"
    if score < 60:
        return "C"
    if score < 80:
        return "D"
    return "E"


def verdict(grade_letter: str) -> str:
    return {
        "A": "clean: no live risky approvals, well diversified",
        "B": "low risk: minor items to tidy",
        "C": "moderate risk: worth cleaning up now",
        "D": "high risk: revoke approvals ASAP",
        "E": "critical: act now (revoke, rotate funds)",
    }.get(grade_letter, "unknown")
