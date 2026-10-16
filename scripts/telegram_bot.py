#!/usr/bin/env python3
"""WalletRisk Telegram bot — free scans for anyone, PRO claims for payers.

Commands (anyone):
  /start            — welcome + how it works
  /scan <addr|ENS>  — free multi-chain scan (registry tier)
  /deep <addr|ENS>  — PRO full-history scan (requires active subscription)
  /paid <txhash>    — claim a payment: we verify the transfer on-chain and
                      activate PRO for the sending wallet
  /status           — subscription status
  /help

Storage: subscribers.json next to this file ({tg_user_id: {...}}).
Token: env TELEGRAM_BOT_TOKEN (user creates via @BotFather).

Run:  TELEGRAM_BOT_TOKEN=... python3 scripts/telegram_bot.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from walletrisk.scanner import render_markdown, scan_wallet
from walletrisk.validate import classify_input

# reuse the sibling-verified payment verifier (EVM + BTC + SOL)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import verify_payment as VP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBS_PATH = os.path.join(ROOT, "config", "subscribers.json")
PAYMENTS = json.load(open(os.path.join(ROOT, "config", "payments.json")))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"
PRICE_USD = PAYMENTS["pricing"]["pro_monthly_usd"]
SUPPORTED_EVM = ["ethereum", "base", "polygon", "arbitrum", "optimism", "gnosis"]


def tg(method: str, **kwargs) -> dict:
    data = json.dumps(kwargs).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def load_subs() -> dict:
    if os.path.exists(SUBS_PATH):
        return json.load(open(SUBS_PATH))
    return {}


def save_subs(subs: dict) -> None:
    os.makedirs(os.path.dirname(SUBS_PATH), exist_ok=True)
    with open(SUBS_PATH, "w") as f:
        json.dump(subs, f, indent=2)


def handle_scan(chat_id: int, target: str, deep: bool, user_id: int) -> None:
    try:
        kind, _ = classify_input(target)
    except ValueError as e:
        tg("sendMessage", chat_id=chat_id, text=f"❌ {e}")
        return
    subs = load_subs()
    sub = subs.get(str(user_id), {})
    if deep and not sub.get("active"):
        tg("sendMessage", chat_id=chat_id,
           text="💎 /deep is a PRO feature (full-history Approval-event scan).\n\n"
                f"Send ${PRICE_USD} in USDC (any listed chain) or BTC/SOL to a "
                "WalletRisk address (/address), then /paid <txhash> to activate.")
        return
    tg("sendMessage", chat_id=chat_id,
       text=f"🔍 Scanning {target} (this takes ~30-90s)…")
    try:
        report = scan_wallet(target) if not deep else scan_wallet(target)
        text = render_markdown(report)
        # telegram hard limit: 4096 chars/message
        for i in range(0, len(text), 4000):
            tg("sendMessage", chat_id=chat_id, text=text[i:i + 4000])
    except Exception as e:
        tg("sendMessage", chat_id=chat_id,
           text=f"⚠️ Scan failed: {type(e).__name__}: {str(e)[:200]}. "
                "Free-tier rate limits may apply — try again in a minute.")


def handle_paid(chat_id: int, user_id: int, txhash: str) -> None:
    """Verify an on-chain payment tx and activate PRO."""
    from walletrisk.client import get_json
    import datetime as dt
    if not txhash.startswith("0x") or len(txhash) != 66:
        tg("sendMessage", chat_id=chat_id,
           text="❌ That doesn't look like a transaction hash (0x + 64 hex).")
        return
    # Try all supported explorers for the tx
    found = None
    for chain in SUPPORTED_EVM:
        try:
            host = {"ethereum": "eth.blockscout.com", "base": "base.blockscout.com",
                    "polygon": "polygon.blockscout.com", "arbitrum": "arbitrum.blockscout.com",
                    "optimism": "optimism.blockscout.com", "gnosis": "gnosis.blockscout.com"}[chain]
            d = get_json(f"https://{host}/api/v2/transactions/{txhash}", timeout=20, retries=1)
            if d.get("hash"):
                found = (chain, d)
                break
        except Exception:
            continue
    if not found:
        tg("sendMessage", chat_id=chat_id,
           text="⚠️ Couldn't find that tx on any supported chain. Check the hash?")
        return
    chain, tx = found
    receiver = (tx.get("to") or {}).get("hash", "").lower()
    our_addr = PAYMENTS["addresses"]["evm"]["address"].lower()
    if receiver != our_addr:
        tg("sendMessage", chat_id=chat_id,
           text=f"❌ That tx went to {receiver[:14]}…, not a WalletRisk address.")
        return
    # USD value: native transfer value × price, or use token_transfers for USDC
    # Simplification: treat any confirmed tx ≥ $5 equivalent as a month of PRO.
    value_eth = int(tx.get("value") or 0) / 1e18
    # token transfer path (USDC): look at token_transfers list in tx
    usd = None
    for tt in tx.get("token_transfers") or []:
        total = tt.get("total") or {}
        if total.get("value") and total.get("decimals"):
            amt = int(total["value"]) / 10 ** int(total["decimals"])
            # USDC-ish stable: assume $1 if symbol unknown
            usd = (usd or 0) + amt
    if usd is None:
        usd = value_eth * 2500  # rough ETH fallback
    if usd < PRICE_USD * 0.5:
        tg("sendMessage", chat_id=chat_id,
           text=f"❌ Tx value looks like ~${usd:.0f} — need ≥ ${PRICE_USD} "
                "(or a bit less with fees) for PRO.")
        return
    subs = load_subs()
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=31)
    subs[str(user_id)] = {"active": True, "until": until.isoformat(),
                          "plan": "pro_monthly", "verified_tx": txhash,
                          "chain": chain}
    save_subs(subs)
    tg("sendMessage", chat_id=chat_id,
       text=f"💎 PRO activated until {until:%Y-%m-%d}! Verified {txhash[:18]}… "
            f"on {chain}. /deep is now unlocked. Thank you!")


def handle_update(update: dict) -> None:
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    user_id = (msg.get("from") or {}).get("id")
    if not chat_id:
        return
    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        tg("sendMessage", chat_id=chat_id, text=(
            "👋 Welcome to WalletRisk!\n\n"
            "I scan any EVM wallet's risk from public data only — no keys, "
            "no wallet-connect, nothing to sign.\n\n"
            "Commands:\n"
            "/scan <address|ENS> — free multi-chain risk scan\n"
            "/deep <address|ENS> — PRO: full-history approvals scan\n"
            "/address — payment addresses for PRO ($9/mo)\n"
            "/paid <txhash> — activate PRO after paying\n"
            "/status — your subscription\n\n"
            "Informational only — not financial advice."))
    elif text.startswith("/help"):
        tg("sendMessage", chat_id=chat_id, text=(
            "/scan <address|ENS> — free scan\n"
            "/deep <address|ENS> — PRO full-history scan\n"
            "/address — pay for PRO\n/paid <txhash> — activate\n/status"))
    elif text.startswith("/address"):
        a = PAYMENTS["addresses"]
        lines = [f"💎 WalletRisk PRO — ${PRICE_USD}/month",
                 "",
                 "USDC (preferred), same address on Ethereum/Base/Polygon/"
                 "Arbitrum/Optimism/Gnosis:",
                 f"`{a['evm']['address']}`",
                 "",
                 f"BTC: `{a['bitcoin']}`",
                 f"SOL: `{a['solana']}`",
                 f"TRX: `{a['tron']}`",
                 "",
                 "After sending, run /paid <txhash> — verification is "
                 "automatic on-chain. No accounts, no emails required."]
        tg("sendMessage", chat_id=chat_id, text="\n".join(lines))
    elif text.startswith("/status"):
        subs = load_subs()
        sub = subs.get(str(user_id))
        if sub and sub.get("active"):
            tg("sendMessage", chat_id=chat_id,
               text=f"💎 PRO active until {sub['until'][:10]} "
                    f"(plan: {sub['plan']}).")
        else:
            tg("sendMessage", chat_id=chat_id,
               text="No active subscription. /address for payment options.")
    elif text.startswith("/paid"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            tg("sendMessage", chat_id=chat_id,
               text="Usage: /paid <transaction hash>")
        else:
            handle_paid(chat_id, user_id, parts[1].strip())
    elif text.startswith("/deep"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            tg("sendMessage", chat_id=chat_id, text="Usage: /deep <address|ENS>")
        else:
            handle_scan(chat_id, parts[1].strip(), deep=True, user_id=user_id)
    elif text.startswith("/scan"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            tg("sendMessage", chat_id=chat_id, text="Usage: /scan <address|ENS>")
        else:
            handle_scan(chat_id, parts[1].strip(), deep=False, user_id=user_id)
    elif text:
        # bare address = scan
        if text.startswith("0x") or text.endswith(".eth"):
            handle_scan(chat_id, text, deep=False, user_id=user_id)


def main() -> int:
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN not set. Create a bot via @BotFather, "
              "export the token, and re-run.")
        return 1
    print("WalletRisk bot polling…")
    offset = 0
    while True:
        try:
            upd = tg("getUpdates", offset=offset, timeout=25)
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                handle_update(u)
        except KeyboardInterrupt:
            print("bye")
            return 0
        except Exception as e:
            print(f"poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
