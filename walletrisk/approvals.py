"""Approvals scanner — free-tier, per-chain strategy:

- ethereum: mevblocker public RPC — full-history getLogs (10M windows) +
  batched eth_call (100/req) for live allowance checks.
- polygon/gnosis/base/arbitrum/optimism: Blockscout eth-rpc getLogs, windowed
  per instance caps, browser UA + spacing (free-tier ~10 rpc/min each).
- zksync: approvals unsupported (its public RPC path is dead) — reported as
  unsupported, never as silently empty.

Event -> state: (token, spender) keyed by latest event block. A live
allowance() call drops revoked pairs. USD at risk = min(allowance, balance) x
current price — an unlimited approval can only take what the wallet holds.
"""

from __future__ import annotations

import time

from .client import (rpc_call, rpc_mainnet, rpc_mainnet_batch, rpc_url_call,
                     ApiError, RateLimitError)
from .chains import host_of

APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
MAX_UINT = (1 << 256) - 1
MAX_UINT_THRESHOLD = MAX_UINT // 2  # >= this counts as "unlimited"

# eth-rpc hosts that differ from the v2 REST host (301-redirected instances)
RPC_HOST_OVERRIDES: dict[str, str] = {
    "optimism": "explorer.optimism.io",
    "gnosis": "gnosisscan.io",
}

# per-instance config: scan window, RPC page cap, history reach (blocks)
APPROVAL_CONFIG: dict[str, dict] = {
    "ethereum": {"window": 10_000_000, "page_cap": 10_000, "history": None},
    "polygon": {"window": 1_000_000, "page_cap": 1_000, "history": 6_000_000},
    "gnosis": {"window": 1_000_000, "page_cap": 1_000, "history": 3_000_000},
    "base": {"window": 1_000_000, "page_cap": 1_000, "history": 4_000_000},
    "arbitrum": {"window": 1_000_000, "page_cap": 1_000, "history": 4_000_000},
    "optimism": {"window": 1_000_000, "page_cap": 1_000, "history": 4_000_000},
    "zksync": None,
}


def approvals_supported(chain: str) -> bool:
    return APPROVAL_CONFIG.get(chain) is not None


def _owner_topic(owner: str) -> str:
    return "0x" + "0" * 24 + owner[2:].lower()


def _addr_from_topic(topic: str) -> str:
    return "0x" + topic[-40:]


def _val_from_data(data: str) -> int:
    if not data or data == "0x":
        return 0
    try:
        return int(data, 16)
    except ValueError:
        return 0


def _allowance_calldata(owner_padded: str, spender: str) -> str:
    """allowance(address owner, address spender) -> selector + two 32-byte words."""
    return "0xdd62ed3e" + owner_padded[2:] + "0" * 24 + spender[2:].lower()


def _split_walk(getter, lo: int, hi: int, page_cap: int,
                depth: int = 0, max_depth: int = 9) -> list[dict]:
    """Walk [lo, hi] via getter(lo, hi); split on error (range too wide) or on
    a full page (truncation risk). Never fakes an empty result on rate limits:
    a rate-limited window returns a marker the caller surfaces."""
    if depth > max_depth or lo > hi:
        return []
    res = getter(lo, hi)
    if res is None:  # rate-limited beyond retries — abort this window loudly
        raise RateLimitError(f"window {lo}-{hi}")
    if isinstance(res, dict) and res.get("error"):
        mid = (lo + hi) // 2
        if mid <= lo:
            return []
        return (_split_walk(getter, lo, mid, page_cap, depth + 1, max_depth)
                + _split_walk(getter, mid + 1, hi, page_cap, depth + 1, max_depth))
    logs = res.get("result", []) if isinstance(res, dict) else []
    if len(logs) >= page_cap:
        mid = (lo + hi) // 2
        if mid <= lo:
            return logs  # cannot split further
        return (_split_walk(getter, lo, mid, page_cap, depth + 1, max_depth)
                + _split_walk(getter, mid + 1, hi, page_cap, depth + 1, max_depth))
    return logs


def _make_getter(host: str | None, owner: str):
    """getter(lo, hi) -> JSON-RPC response dict, or None if rate-limited
    beyond retries (so the walker can raise instead of faking empty)."""
    ot = _owner_topic(owner)

    def call(lo: int, hi: int):
        params = [{"fromBlock": hex(lo), "toBlock": hex(hi),
                   "topics": [APPROVAL_TOPIC, ot]}]
        try:
            if host is None:  # mainnet via mevblocker
                return rpc_mainnet("eth_getLogs", params)
            return rpc_call(host, "eth_getLogs", params)
        except RateLimitError:
            return None

    return call


def fetch_approval_events(chain: str, owner: str) -> list[dict]:
    """All ERC-20 Approval events for owner on chain, within the configured
    history window. Raises on hard rate limits (never returns fake-empty)."""
    cfg = APPROVAL_CONFIG.get(chain)
    if cfg is None:
        raise ApiError(0, f"approvals unsupported on {chain!r}", chain)
    host = None if chain == "ethereum" else RPC_HOST_OVERRIDES.get(chain, host_of(chain))
    if host is None:
        tip_res = rpc_mainnet("eth_blockNumber", [])
    else:
        tip_res = rpc_call(host, "eth_blockNumber", [])
    if "result" not in tip_res:
        raise ApiError(0, f"no tip on {chain}: {tip_res}", host or "mevblocker")
    tip = int(tip_res["result"], 16)

    getter = _make_getter(host, owner)
    start = 0 if cfg["history"] is None else max(0, tip - cfg["history"])
    out: list[dict] = []
    lo = start
    while lo <= tip:
        hi = min(tip, lo + cfg["window"] - 1)
        out.extend(_split_walk(getter, lo, hi, cfg["page_cap"]))
        lo = hi + 1
    return out


def parse_approval_events(logs: list[dict]) -> dict[str, dict]:
    """Collapse events into (token, spender) -> latest approval state."""
    out: dict[str, dict] = {}
    for log in logs:
        topics = log.get("topics", [])
        if len(topics) < 3:
            continue
        token = log["address"].lower()
        spender = _addr_from_topic(topics[2]).lower()
        value = _val_from_data(log.get("data", "0x"))
        key = f"{token}|{spender}"
        prev = out.get(key)
        block = int(log["blockNumber"], 16)
        if prev is None or block >= prev["block"]:
            out[key] = {"token": token, "spender": spender, "value": value,
                        "block": block, "tx": log.get("transactionHash")}
    return out


def _known_spender_name(addr: str) -> str | None:
    """Reverse-lookup a spender address in the curated registry."""
    try:
        from .registry import _SPENDERS
        for name, chains, saddr in _SPENDERS:
            if saddr == addr.lower():
                return name
    except Exception:
        pass
    return None


def check_live(chain: str, owner: str, approvals: dict[str, dict],
               token_meta: dict[str, dict], batch_size: int = 100
               ) -> tuple[list[dict], int]:
    """Live allowance() confirmation for every (token, spender) pair.
    Mainnet: batched via mevblocker. Other chains: sequential Blockscout calls
    (rate-limited; skipped pairs are counted, not dropped silently).
    Returns (live_approvals, skipped_count)."""
    pairs = list(approvals.values())
    live: list[dict] = []
    skipped = 0
    owner_padded = "0x" + "0" * 24 + owner[2:].lower()

    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i:i + batch_size]
        results: list = []
        if chain == "ethereum":
            calls = [{"method": "eth_call",
                      "params": [{"to": ap["token"],
                                  "data": _allowance_calldata(owner_padded, ap["spender"])},
                                 "latest"]} for ap in chunk]
            try:
                resp = rpc_mainnet_batch(calls)
            except (RateLimitError, ApiError):
                time.sleep(8)
                resp = rpc_mainnet_batch(calls)
            results = resp if isinstance(resp, list) else []
        else:
            from .chains import rpc_of
            for ap in chunk:
                try:
                    r = rpc_url_call(rpc_of(chain), "eth_call",
                                     [{"to": ap["token"],
                                       "data": _allowance_calldata(owner_padded, ap["spender"])},
                                      "latest"])
                    results.append(r)
                except RateLimitError:
                    skipped += 1
                except ApiError:
                    results.append({"error": "call-failed"})

        for ap, r in zip(chunk, results):
            if not isinstance(r, dict) or r.get("error"):
                skipped += 1
                continue
            result = r.get("result") or "0x"
            if result == "0x":
                skipped += 1
                continue
            try:
                allowance = int(result, 16)
            except ValueError:
                skipped += 1
                continue
            if allowance <= 0:
                continue  # revoked — legitimately dropped
            meta = token_meta.get(ap["token"], {})
            if not meta.get("symbol") or meta.get("symbol") == "Unknown":
                # dormant token not in the holdings snapshot — fetch meta
                from .token_meta import token_meta as fetch_meta
                host = host_of(chain)
                fetched = fetch_meta(host, ap["token"])
                if fetched:
                    meta = fetched
            try:
                decimals = int(meta.get("decimals", 18) or 18)
            except (TypeError, ValueError):
                decimals = 18
            rate = float(meta.get("rate") or meta.get("exchange_rate") or 0)
            allowance_tokens = allowance / 10 ** decimals
            balance = float(meta.get("balance") or 0)
            if balance:
                # can only lose what you hold: exposure = min(allowance, balance)
                exposure_tokens = min(allowance_tokens, balance)
            else:
                # dormant: wallet holds none — exposure unknowable, not fake-huge
                exposure_tokens = None
            live.append({
                "token": ap["token"],
                "symbol": meta.get("symbol", "Unknown"),
                "spender": ap["spender"],
                "spender_name": _known_spender_name(ap["spender"]),
                "allowance_raw": allowance,
                "unlimited": allowance >= MAX_UINT_THRESHOLD,
                "allowance_tokens": allowance_tokens,
                "usd_value_at_risk": exposure_tokens * rate if (exposure_tokens is not None and rate) else None,
                "approved_block": ap["block"],
            })
    if skipped:
        live = live or []
    live.sort(key=lambda a: (-(a.get("usd_value_at_risk") or 0),
                             -a.get("approved_block", 0)))
    return live, skipped
