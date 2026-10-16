"""Token metadata fetcher — fills symbols/decimals/rates for ANY token address
(vital for dormant-approval tokens the wallet no longer holds, which never
appear in the holdings snapshot). Keyless Blockscout v2, browser UA, cached."""

from __future__ import annotations

from .client import get_json

_cache: dict[tuple[str, str], dict] = {}


def token_meta(host: str, token: str, timeout: int = 30) -> dict:
    """{symbol, name, decimals, rate, reputation} — cached per (host, token)."""
    key = (host, token.lower())
    if key in _cache:
        return _cache[key]
    try:
        d = get_json(f"https://{host}/api/v2/tokens/{token}", timeout=timeout, retries=2)
    except Exception:
        d = {}
    meta = {
        "symbol": d.get("symbol") or "Unknown",
        "name": d.get("name") or d.get("symbol") or "Unknown token",
        "decimals": d.get("decimals") or 18,
        "rate": d.get("exchange_rate"),
        "reputation": d.get("reputation"),
    }
    _cache[key] = meta
    return meta
