"""Live on-chain checks: allowance(owner, spender) for ERC-20 and
isApprovedForAll(owner, operator) for NFTs — read-only eth_call via
publicnode (CORS-open, no key). Results are chain truth, not heuristics."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import post_json, ApiError

ALLOWANCE = "0xdd62ed3e"          # allowance(address,address)
IS_APPROVED_FOR_ALL = "0xe985e9c5"  # isApprovedForAll(address,address)
UNLIMITED_THRESHOLD = 1 << 255    # values >= this are "infinite" approvals

MAX_PAIRS_PER_CHAIN = 350
CONCURRENCY = 8


def _pad(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def eth_call(rpc: str, to: str, data: str, timeout: int = 20) -> str | None:
    d = post_json(rpc, {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                        "params": [{"to": to, "data": data}, "latest"]},
                  timeout=timeout, retries=1)
    if isinstance(d, dict) and "result" in d:
        r = d["result"]
        return r if r and r != "0x" else "0x0"
    return None


def check_allowance(rpc: str, token: str, owner: str, spender: str) -> int | None:
    """Live ERC-20 allowance. None = call failed (revert/no contract)."""
    data = ALLOWANCE + _pad(owner) + _pad(spender)
    res = eth_call(rpc, token, data)
    if res is None:
        return None
    try:
        return int(res, 16)
    except ValueError:
        return None


def check_is_approved_for_all(rpc: str, nft: str, owner: str, operator: str) -> bool | None:
    data = IS_APPROVED_FOR_ALL + _pad(owner) + _pad(operator)
    res = eth_call(rpc, nft, data)
    if res is None:
        return None
    try:
        return int(res, 16) == 1
    except ValueError:
        return None


def batch_allowances(rpc: str, owner: str, pairs: list[dict],
                     budget: int = MAX_PAIRS_PER_CHAIN) -> list[dict]:
    """pairs: [{token, spender, token_meta..., spender_meta...}] -> live values.
    Deduplicated, budgeted, concurrent. Returns only pairs with a live value."""
    seen: set[tuple[str, str]] = set()
    queue = []
    for p in pairs:
        key = (p["token"], p["spender"])
        if key in seen:
            continue
        seen.add(key)
        queue.append(p)
    queue = queue[:budget]

    out: list[dict] = []
    lock = threading.Lock()

    def work(p):
        val = check_allowance(rpc, p["token"], owner, p["spender"])
        if val is None:
            return None
        r = dict(p)
        r["allowance_raw"] = val
        r["unlimited"] = val >= UNLIMITED_THRESHOLD
        return r

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(work, p): p for p in queue}
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except (ApiError, Exception):
                r = None
            if r:
                with lock:
                    out.append(r)
    return out


def batch_nft_approvals(rpc: str, owner: str, nfts: list[dict],
                        operators: list[dict]) -> list[dict]:
    """nfts: [{address, symbol, ...}], operators: [{address, registry_name}]"""
    seen: set[tuple[str, str]] = set()
    queue = []
    for nft in nfts:
        for op in operators:
            key = (nft["address"], op["address"])
            if key in seen:
                continue
            seen.add(key)
            queue.append((nft, op))
    out = []
    lock = threading.Lock()

    def work(pair):
        nft, op = pair
        approved = check_is_approved_for_all(rpc, nft["address"], owner, op["address"])
        if approved is None or not approved:
            return None
        return {"nft": nft, "operator": op, "approved_for_all": True}

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        for fut in as_completed({ex.submit(work, q): q for q in queue}):
            try:
                r = fut.result()
            except Exception:
                r = None
            if r:
                with lock:
                    out.append(r)
    return out
