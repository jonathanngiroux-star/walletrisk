"""Render report dicts into markdown / plain text for Telegram, X, and web."""

from __future__ import annotations

import datetime as dt


def _fmt_usd(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v/1e6:,.2f}M"
    if v >= 1_000:
        return f"${v/1e3:,.1f}k"
    if v >= 1:
        return f"${v:,.2f}"
    if v > 0:
        return f"${v:.4f}"
    return "$0"


def _fmt_amt(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"{v/1e6:,.2f}M"
    if v >= 1_000:
        return f"{v/1e3:,.1f}k"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _bar(score: int, width: int = 20) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def markdown(r: dict, deep: bool = False) -> str:
    """Full markdown report. `deep=True` adds per-approval detail (paid tier)."""
    lines: list[str] = []
    g = r["grade"]
    emoji = {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "E": "🔴"}[g]
    title = f"# {emoji} WalletRisk Report — {r['address_short']}"
    if r.get("resolved_from"):
        title += f" ({r['resolved_from']})"
    lines.append(title)
    lines.append("")
    lines.append(f"**Grade {g} · Overall risk {r['scores']['overall']}/100** — "
                 f"{r['verdict']}")
    lines.append("")
    lines.append(f"**Portfolio value:** {_fmt_usd(r['total_usd'])} across "
                 f"{len(r['chains_scanned'])} chains · scanned "
                 f"{r['generated_at'][:10]}")
    lines.append("")

    # score bars
    lines.append("## Risk breakdown")
    lines.append("```")
    lines.append(f"approvals      {_bar(r['scores']['approvals'])} {r['scores']['approvals']}/100")
    lines.append(f"concentration  {_bar(r['scores']['concentration'])} {r['scores']['concentration']}/100")
    lines.append(f"dormancy       {_bar(r['scores']['dormancy'])} {r['scores']['dormancy']}/100")
    lines.append("```")
    lines.append("")

    # holdings
    if r["total_usd"] > 0:
        lines.append("## Holdings (top)")
        rows = []
        for c, s in r["per_chain"].items():
            if s["native"]["usd"] > 0:
                rows.append((s["native"]["symbol"], c, s["native"]["usd"],
                             s["native"]["balance"]))
            for t in s["tokens"][:8]:
                if t["usd"] > 0:
                    rows.append((t["symbol"], c, t["usd"], t["amount"]))
        rows.sort(key=lambda x: x[2], reverse=True)
        lines.append("| Asset | Chain | Amount | Value |")
        lines.append("|---|---|---|---|")
        for sym, c, usd, amt in rows[:12]:
            lines.append(f"| {sym} | {c} | {_fmt_amt(amt)} | {_fmt_usd(usd)} |")
        lines.append("")

    # approvals
    appr = r["approvals"]["live"]
    unl = r["approvals"]["unlimited"]
    lines.append("## Token approvals (live)")
    lines.append(f"Scanned Approval events back through history: "
                 f"{r['approvals']['events_scanned']} events → "
                 f"**{len(appr)} live approvals**, {len(unl)} unlimited ⚠️")
    if appr:
        lines.append("")
        lines.append("| Token | Chain | Spender | Allowance |")
        lines.append("|---|---|---|---|")
        shown = appr if deep else appr[:6]
        for a in shown:
            name = a.get("spender_name")
            spender = f"{name} `{a['spender'][:10]}…`" if name else f"`{a['spender'][:10]}…`"
            allw = "∞ UNLIMITED" if a["unlimited"] else _fmt_amt(a.get("allowance_tokens"))
            lines.append(f"| {a['symbol']} | {a['chain']} | {spender} | {allw} |")
        if not deep and len(appr) > 6:
            lines.append(f"| … | | | +{len(appr)-6} more (deep report) |")
    if unl:
        lines.append("")
        lines.append("⚠️ **Unlimited approvals found.** Anyone controlling those "
                     "spender contracts can take the approved tokens at any time. "
                     "Revoke via revoke.cash or ethallowance.com.")
    lines.append("")

    # activity
    act = r["activity"]
    if act.get("days_idle") is not None:
        lines.append(f"**Last activity:** {act['days_idle']:.0f} days ago · "
                     f"{act['tx_count']:,} txs on record")
    if r.get("chain_errors"):
        lines.append("")
        lines.append(f"_Data gaps: {len(r['chain_errors'])} chain/API errors "
                     f"(free-tier limits) — totals may be partial._")
    lines.append("")
    lines.append("_Informational only — not financial advice. Data: Blockscout "
                 "& CoinGecko public APIs._")
    return "\n".join(lines)


def telegram(r: dict) -> str:
    """Compact plain-text report for Telegram (no markdown tables)."""
    g = r["grade"]
    emoji = {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "E": "🔴"}[g]
    s = r["scores"]
    L = [f"{emoji} *WalletRisk* — `{r['address_short']}`",
         f"Grade *{g}* · risk {s['overall']}/100 ({r['verdict']})",
         f"Portfolio: *{_fmt_usd(r['total_usd'])}*"]
    appr = r["approvals"]["live"]
    unl = r["approvals"]["unlimited"]
    L.append(f"Approvals: {len(appr)} live, {len(unl)} unlimited ⚠️" if appr
             else "Approvals: none live ✓")
    if unl:
        for a in unl[:5]:
            L.append(f"  ∞ {a['symbol']} → `{a['spender'][:14]}…` ({a['chain']})")
    act = r["activity"]
    if act.get("days_idle") is not None:
        L.append(f"Last active: {act['days_idle']:.0f}d ago ({act['tx_count']:,} txs)")
    L.append("_Not financial advice · free public data_")
    return "\n".join(L)


def x_post(r: dict) -> str:
    """≤280-char daily example post."""
    g = r["grade"]
    emoji = {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "E": "🔴"}[g]
    s = r["scores"]
    appr = r["approvals"]["live"]
    unl = r["approvals"]["unlimited"]
    txt = (f"{emoji} WalletRisk daily: {r['address_short']}\n"
           f"Portfolio {_fmt_usd(r['total_usd'])} | Grade {g} "
           f"(risk {s['overall']}/100)\n"
           f"{len(appr)} live approvals, {len(unl)} unlimited\n"
           f"Free report: github.com/walletrisk")
    if len(txt) > 275:
        txt = txt[:272] + "…"
    return txt
