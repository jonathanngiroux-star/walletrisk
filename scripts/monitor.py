#!/usr/bin/env python3
"""PRO alert engine — daily re-scan of subscribed wallets, diff vs last state,
alert on new/changed HIGH findings (the paid tier's core value).

State: config/subscribers.json (tg_user_id -> {wallets: [...], last_state: {...}})
Run by cron: scripts/monitor.py [--notify]

Without --notify, prints the diff to stdout (dry-run mode).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walletrisk.scanner import scan_wallet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBS_PATH = os.path.join(ROOT, "config", "subscribers.json")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


def load_subs() -> dict:
    if os.path.exists(SUBS_PATH):
        return json.load(open(SUBS_PATH))
    return {}


def save_subs(subs: dict) -> None:
    os.makedirs(os.path.dirname(SUBS_PATH), exist_ok=True)
    with open(SUBS_PATH, "w") as f:
        json.dump(subs, f, indent=2)


def wallet_fingerprint(report: dict) -> dict:
    """Compact comparable state: set of HIGH/MEDIUM findings."""
    out = []
    for c in report["chains"]:
        for f in c.get("findings", []):
            out.append({
                "chain": c["chain"],
                "token": f.get("token"),
                "spender": f.get("spender"),
                "severity": f.get("severity"),
                "unlimited": f.get("unlimited"),
                "exposure_usd": f.get("exposure_usd"),
            })
    return {"grade": report["grade"], "findings": sorted(
        out, key=lambda x: str(x))}


def diff_states(old: dict, new: dict) -> list[str]:
    alerts = []
    if old is None:
        if new["findings"]:
            alerts.append(f"Baseline established: {len(new['findings'])} findings, "
                          f"grade {new['grade']}.")
        return alerts
    if old.get("grade") != new["grade"]:
        alerts.append(f"Grade changed {old.get('grade')} → {new['grade']}.")
    old_keys = {(f["chain"], f["token"], f["spender"]) for f in old.get("findings", [])}
    new_keys = {(f["chain"], f["token"], f["spender"]) for f in new["findings"]}
    for f in new["findings"]:
        k = (f["chain"], f["token"], f["spender"])
        if k not in old_keys:
            alerts.append(f"NEW {f['severity']}: {f['chain']} — "
                          f"{f.get('token') or '?'} → {f.get('spender', '')[:12]}… "
                          f"(unlimited: {f.get('unlimited')})")
    for f in old.get("findings", []):
        k = (f["chain"], f["token"], f["spender"])
        if k not in new_keys:
            alerts.append(f"RESOLVED: {f['chain']} — {f.get('token')} approval "
                          f"to {f.get('spender', '')[:12]}… is gone. 🎉")
    return alerts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true",
                    help="send alerts via Telegram (else print dry-run)")
    args = ap.parse_args()

    subs = load_subs()
    active = {uid: s for uid, s in subs.items()
              if s.get("active") and s.get("wallets")}
    if not active:
        print("no active subscribers with wallets to monitor")
        return 0

    for uid, s in active.items():
        for wallet in s.get("wallets", [])[:3]:  # cap per user
            print(f"scanning {wallet} (user {uid})…")
            try:
                report = scan_wallet(wallet)
            except Exception as e:
                print(f"  scan failed: {e}")
                continue
            new_state = wallet_fingerprint(report)
            old_state = s.get("last_state", {}).get(wallet)
            alerts = diff_states(old_state, new_state)
            s.setdefault("last_state", {})[wallet] = new_state
            if alerts:
                text = "🚨 WalletRisk alert\n" + "\n".join(alerts[:10])
                if args.notify and TOKEN:
                    import urllib.request
                    url = (f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                           f"?chat_id={uid}&text={urllib.parse.quote(text[:4000])}")
                    urllib.request.urlopen(url, timeout=30)
                    print(f"  -> alerted {uid}")
                else:
                    print(f"  [dry-run] would alert {uid}:\n{text}")
            else:
                print("  no changes")
    save_subs(subs)
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa
    sys.exit(main())
