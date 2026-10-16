"""Discovery: what does this wallet hold, and which contracts has it ever
interacted with? Blockscout v2 REST, browser UA, paged, retried, read-only.

Honesty note: approvals granted inside a router call do not appear as the
tx 'to' (the router does). The interaction set is therefore candidates, not
ground truth; the live allowance() check is ground truth."""

from __future__ import annotations

import time
from urllib.parse import urlencode

from .client import blockscout, get_json

MAX_TOKEN_PAGES = 3          # 50/page -> up to 150 holdings
MAX_TX_PAGES = 4             # 50/page -> up to 200 txs per chain
MAX_TOKEN_TRANSFER_PAGES = 2
MAX_TOKENS = 40              # cap tokens actually checked
MAX_SPENDERS = 200           # cap unique spender candidates
PAGE_TIME_BUDGET_S = 30      # a single page slower than this ends pagination


def fetch_holdings(host: str, address: str) -> list[dict]:
    """Current token holdings, most valuable first. Normalized dicts:
    {address, symbol, name, decimals, kind, raw_balance, usd_value, exchange_rate}"""
    items: list[dict] = []
    for page in range(MAX_TOKEN_PAGES):
        params = None
        if page > 0 and items and items[-1].get("_page"):
            params = items[-1]["_page"]
        # heavy wallets make this endpoint slow: patient timeout, 3 retries,
        # and a per-page time budget — pagination ends when a page stalls.
        # (blockscout() drops JSON-null params like fiat_value=None which
        #  urlencode would serialize as the literal string "None" -> HTTP 422)
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        d = blockscout(host, f"/addresses/{address}/tokens", params=clean or None)
        t0 = time.time() - 0  # keep names tidy below
        if page > 0 and (time.time() - t0) > PAGE_TIME_BUDGET_S:
            break
        batch = d.get("items", [])
        nxt = d.get("next_page_params")
        for it in batch:
            tok = it.get("token") or {}
            items.append({
                "address": (tok.get("address_hash") or tok.get("address") or "").lower(),
                "symbol": tok.get("symbol") or "?",
                "name": tok.get("name") or tok.get("symbol") or "Unknown token",
                "decimals": int(tok.get("decimals") or 18),
                "kind": tok.get("type") or "ERC-20",
                "raw_balance": int(it.get("value") or 0),
                "exchange_rate": tok.get("exchange_rate"),
                "reputation": tok.get("reputation"),
                "icon_url": tok.get("icon_url"),
                "_page": nxt,
            })
        if not nxt:
            break
    for t in items:
        t.pop("_page", None)
    fungible = [t for t in items if t["raw_balance"] > 0]
    fungible.sort(key=lambda t: -(t["raw_balance"] * float(t["exchange_rate"] or 0)))
    return fungible[:MAX_TOKENS]


def fetch_native(host: str, address: str) -> dict:
    d = blockscout(host, f"/addresses/{address}")
    return {
        "raw_balance": int(d.get("coin_balance") or 0),
        "exchange_rate": d.get("exchange_rate"),
        "last_active": None,  # filled from txs below
    }


def fetch_interactions(host: str, address: str) -> tuple[list[str], dict]:
    """Candidate spender addresses from the wallet's own history.
    Returns (unique lowercased 'to' contract candidates, meta)."""
    candidates: dict[str, int] = {}
    last_tx_time = None
    first_tx_time = None
    pages_meta = {"tx_pages": 0, "transfer_pages": 0}
    for _ in range(MAX_TX_PAGES):
        params = None
        if pages_meta["tx_pages"] > 0 and last_params:
            params = last_params
        d = blockscout(host, f"/addresses/{address}/transactions", params=params)
        last_params = d.get("next_page_params")
        pages_meta["tx_pages"] += 1
        for it in d.get("items", []):
            ts = it.get("timestamp")
            if ts:
                if last_tx_time is None or ts > last_tx_time:
                    last_tx_time = ts
                if first_tx_time is None or ts < first_tx_time:
                    first_tx_time = ts
            to = (it.get("to") or {}).get("hash")
            frm = (it.get("from") or {}).get("hash")
            if to and to.lower() != address.lower():
                candidates[to.lower()] = candidates.get(to.lower(), 0) + 1
            if frm and frm.lower() != address.lower():
                # a contract 'from' can't pull tokens without approval either
                candidates[frm.lower()] = candidates.get(frm.lower(), 0) + 1
        if not last_params:
            break
    last_params = None
    for _ in range(MAX_TOKEN_TRANSFER_PAGES):
        params = last_params if last_params else None
        d = blockscout(host, f"/addresses/{address}/token-transfers", params=params)
        last_params = d.get("next_page_params")
        pages_meta["transfer_pages"] += 1
        for it in d.get("items", []):
            for side in ("from", "to"):
                h = (it.get(side) or {}).get("hash")
                if h and h.lower() != address.lower():
                    candidates[h.lower()] = candidates.get(h.lower(), 0) + 1
        if not last_params:
            break
    ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
    return [a for a, _ in ranked[:MAX_SPENDERS]], {
        "last_active": last_tx_time, "first_active": first_tx_time, **pages_meta,
    }


def resolve_ens(name: str) -> str:
    """ENS -> address via Blockscout search (ens_domain items carry
    ens_info.name + address_hash). Single source: it's the one that works."""
    res = get_json("https://eth.blockscout.com/api/v2/search?q=" + _quote(name),
                   timeout=20, retries=2)
    for item in res.get("items", []):
        if item.get("type") == "ens_domain":
            addr = (item.get("ens_info") or {}).get("address_hash") or item.get("address_hash")
            if addr:
                return addr.lower()
        # older shape: address items named after the ENS
        if item.get("type") == "address" and (item.get("ens_info") or {}).get("address"):
            ens = item["ens_info"]
            if (ens.get("name") or "").lower() == name.lower():
                return ens["address"].lower()
    raise ValueError(f"could not resolve ENS name {name!r}")


from urllib.parse import quote as _quote  # noqa: E402
