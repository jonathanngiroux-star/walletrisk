#!/usr/bin/env python3
"""Generate daily/weekly WalletRisk content posts from REAL scans.

Each post is derived from an actual report produced by the engine — no
fabricated data. Output is written to content/daily/YYYY-MM-DD/ with:
  - x_post.txt      (≤280 chars, ready for xurl post)
  - thread.txt      (X thread: hook + breakdown + CTA)
  - telegram.txt    (channel broadcast)
  - report.md       (full engine output for the link/attachment)

Usage:
  python3 scripts/gen_content.py --wallet vitalik.eth      # daily example
  python3 scripts/gen_content.py --digest                  # weekly digest
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walletrisk import format as fmt
from walletrisk.report import analyze

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content", "daily")

HOOKS = [
    "Today's free wallet risk scan:",
    "What does your wallet look like to an attacker?",
    "Wallet risk, in plain numbers:",
    "Free scan, real on-chain data:",
]

CTAS = [
    "Run yours: github.com/walletrisk/walletrisk",
    "Free tool, no wallet connect, no keys — just an address.",
    "Scan any wallet in seconds. Link below.",
]


def fmt_usd(v):
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v/1e6:.2f}M"
    if v >= 1_000:
        return f"${v/1e3:,.0f}k"
    if v >= 1:
        return f"${v:,.0f}"
    return f"${v:.2f}"


def gen_daily(wallet: str, chains: list[str] | None = None) -> str | None:
    r = analyze(wallet, chains=chains, with_approvals=False)
    day_dir = os.path.join(CONTENT, r["generated_at"][:10])
    os.makedirs(day_dir, exist_ok=True)
    with open(os.path.join(day_dir, "report.md"), "w") as f:
        f.write(fmt.markdown(r))
    with open(os.path.join(day_dir, "report.json"), "w") as f:
        json.dump(r, f, indent=2, default=str)

    s = r["scores"]
    appr = r["approvals"]
    hook = random.choice(HOOKS)
    cta = random.choice(CTAS)

    # single X post (≤280)
    x_post = (f"{hook}\n\n{r['address_short']} · grade {r['grade']} "
              f"(risk {s['overall']}/100)\n"
              f"• {fmt_usd(r['total_usd'])} across {len(r['chains_scanned'])} chains\n"
              f"• {len(appr['live'])} live approvals, {len(appr['unlimited'])} unlimited\n"
              f"\n{cta}")
    if len(x_post) > 280:
        x_post = x_post[:277] + "…"
    with open(os.path.join(day_dir, "x_post.txt"), "w") as f:
        f.write(x_post)

    # thread
    th = [f"{hook} {r['address_short']}, grade {r['grade']} "
          f"(risk {s['overall']}/100). {cta} 🧵",
          f"1/ Portfolio: {fmt_usd(r['total_usd'])} across {len(r['chains_scanned'])} chains. "
          f"Top holdings: " + ", ".join(
              f"{t['symbol']} ({fmt_usd(t['usd'])})"
              for c2, s2 in r["per_chain"].items() for t in s2["tokens"][:2]
              if t["usd"] > 0)[:180],
          f"2/ Approvals: {len(appr['live'])} live, {len(appr['unlimited'])} unlimited. "
          f"An unlimited approval lets the spender contract take the token anytime — "
          f"revoke.cash lists yours for free.",
          f"3/ Concentration {s['concentration']}/100 · dormancy {s['dormancy']}/100. "
          f"Everything above is public on-chain data; nothing was fabricated.",
          f"4/ Want yours scanned? Drop an address below or use the free tool. "
          f"Not financial advice — information only."]
    with open(os.path.join(day_dir, "thread.txt"), "w") as f:
        f.write("\n\n".join(th))

    # telegram
    with open(os.path.join(day_dir, "telegram.txt"), "w") as f:
        f.write(fmt.telegram(r) + f"\n\n{cta}")

    print(f"content for {wallet} -> {day_dir}")
    print("--- X POST ---")
    print(x_post)
    return day_dir


def gen_weekly_digest(week_dir: str | None = None) -> str:
    """Weekly digest: aggregate the week's content dirs + repo state."""
    now = dt.datetime.now(dt.timezone.utc)
    week_start = now - dt.timedelta(days=now.weekday())
    days = []
    root = CONTENT
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if os.path.isfile(os.path.join(p, "x_post.txt")):
            try:
                if dt.date.fromisoformat(d) >= week_start.date():
                    days.append(d)
            except ValueError:
                continue
    lines = [f"📊 WalletRisk weekly digest — {now:%Y-%m-%d}",
             "",
             f"Published {len(days)} daily scans this week: {', '.join(days) or '—'}",
             "",
             "What WalletRisk checks (all public data, zero keys):",
             "• Token approvals — unlimited approvals are the #1 drain vector",
             "• Concentration — how exposed you are to one asset",
             "• Dormancy — stale approvals on idle wallets",
             "• NFT approvals-for-all — whole collections exposed",
             "",
             "Free tier: instant scan, any wallet, 6 chains.",
             "PRO ($9/mo): daily monitoring alerts + full-history deep scan.",
             "",
             "Not financial advice. Information only."]
    out = week_dir or os.path.join(CONTENT, now.strftime("week-%G-W%V"))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "weekly_digest.txt"), "w") as f:
        f.write("\n".join(lines))
    print(f"weekly digest -> {out}")
    print("\n".join(lines))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", help="wallet to scan for the daily example")
    ap.add_argument("--chains", default=None)
    ap.add_argument("--digest", action="store_true")
    args = ap.parse_args()
    if args.digest:
        gen_weekly_digest()
    elif args.wallet:
        chains = args.chains.split(",") if args.chains else None
        gen_daily(args.wallet, chains)
    else:
        ap.print_help()
