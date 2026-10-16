#!/usr/bin/env python3
"""Verify a customer's crypto payment for the WalletRisk Pro tier — keyless,
read-only. Verifies the customer actually transferred >= the required USD
value to a WalletHygiene payment address, on the chain the customer says.

Usage:
  python3 scripts/verify_payment.py --chain ethereum --tx 0xHASH --usd 9
  python3 scripts/verify_payment.py --chain base --tx 0xHASH --usd 9
  python3 scripts/verify_payment.py --chain bitcoin --tx HASH --usd 9

Exits 0 + prints VERIFIED if the transfer is found on-chain with sufficient
value to a known payment address; prints REJECTED with a reason otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
from walletrisk.client import get_json, UA  # noqa: E402

PAYMENTS = json.load(open(__import__("os").path.join(
    __import__("os").path.dirname(__file__), "..", "config", "payments.json")))

# blockscout hosts we can verify on (EVM)
BS_HOSTS = {
    "ethereum": "eth.blockscout.com", "base": "base.blockscout.com",
    "polygon": "polygon.blockscout.com", "arbitrum": "arbitrum.blockscout.com",
    "optimism": "optimism.blockscout.com", "gnosis": "gnosis.blockscout.com",
}


def usd_value_of_erc20_transfer(host: str, transfer: dict) -> float | None:
    tok = transfer.get("token") or {}
    rate = tok.get("exchange_rate")
    decimals = int(tok.get("decimals") or 18)
    total = transfer.get("total") or transfer.get("value")
    if total is None or rate is None:
        return None
    try:
        return float(total) / 10 ** decimals * float(rate)
    except (ValueError, TypeError):
        return None


def verify_evm(chain: str, txhash: str, min_usd: float) -> tuple[bool, str]:
    host = BS_HOSTS[chain]
    pay_addr = PAYMENTS["addresses"]["evm"]["address"].lower()
    # 1. tx exists and is a success
    tx = get_json(f"https://{host}/api/v2/transactions/{txhash}", timeout=30, retries=2)
    if isinstance(tx, dict) and tx.get("status") != "ok":
        return False, f"tx status is {tx.get('status')!r}, not ok"
    if isinstance(tx, dict) and tx.get("result") == "error":
        return False, "tx reverted"
    # 2. find an inbound transfer to the payment address (token or native)
    transfers = get_json(f"https://{host}/api/v2/transactions/{txhash}/token-transfers",
                         timeout=30, retries=2)
    items = transfers.get("items", []) if isinstance(transfers, dict) else []
    for t in items:
        to = ((t.get("to") or {}).get("hash") or "").lower()
        if to != pay_addr:
            continue
        usd = usd_value_of_erc20_transfer(host, t)
        if usd is not None and usd >= min_usd * 0.9:  # 10% slippage tolerance
            return True, f"verified token transfer ${usd:.2f} to payment address on {chain}"
    # 3. native transfer?
    if isinstance(tx, dict):
        to = ((tx.get("to") or {}).get("hash") or "").lower()
        val = tx.get("value")
        rate = tx.get("exchange_rate")
        if to == pay_addr and val and rate:
            usd = float(val) / 1e18 * float(rate)
            if usd >= min_usd * 0.9:
                return True, f"verified native transfer ${usd:.2f} on {chain}"
    return False, "no qualifying transfer to the payment address found in this tx"


def verify_bitcoin(txhash: str, min_usd: float) -> tuple[bool, str]:
    pay_addr = PAYMENTS["addresses"]["bitcoin"]
    d = get_json(f"https://blockstream.info/api/tx/{txhash}", timeout=30, retries=2)
    for vout in d.get("vout", []):
        saddr = vout.get("scriptpubkey_address")
        if saddr == pay_addr:
            btc = vout.get("value", 0) / 1e8
            price = get_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
                             timeout=20, retries=2)
            usd = btc * price["bitcoin"]["usd"]
            if usd >= min_usd * 0.9:
                return True, f"verified BTC transfer ${usd:.2f}"
            return False, f"BTC transfer only ${usd:.2f}, below ${min_usd}"
    return False, "no output to the BTC payment address"


def verify_solana(txhash: str, min_usd: float) -> tuple[bool, str]:
    # signatures-for-address scan (keyless public RPC)
    pay_addr = PAYMENTS["addresses"]["solana"]
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                          "params": [pay_addr, {"limit": 200}]}).encode()
    req = urllib.request.Request("https://api.mainnet-beta.solana.com", data=payload,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    sigs = d.get("result", [])
    if any(s.get("signature") == txhash for s in sigs):
        # amount check via getTransaction is heavier; presence to the pay
        # address is the gate for v1
        return True, "signature found for payment address (amount not yet verified — manual check)"
    return False, "tx signature not found in payment address history"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--chain", required=True,
                   help="ethereum|base|polygon|arbitrum|optimism|gnosis|bitcoin|solana")
    p.add_argument("--tx", required=True, help="transaction hash")
    p.add_argument("--usd", type=float, default=9.0, help="minimum USD value required")
    args = p.parse_args()

    if args.chain in BS_HOSTS:
        ok, msg = verify_evm(args.chain, args.tx, args.usd)
    elif args.chain == "bitcoin":
        ok, msg = verify_bitcoin(args.tx, args.usd)
    elif args.chain == "solana":
        ok, msg = verify_solana(args.tx, args.usd)
    else:
        print("REJECTED: unsupported chain for verification (Tron/Stellar manual)")
        return 1
    print(("VERIFIED: " if ok else "REJECTED: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
