"""Balances + token portfolio per chain, and multi-chain aggregation.

From Blockscout v2:
  /addresses/{a}            -> native balance, ENS, exchange_rate
  /addresses/{a}/token-balances -> 8k+ entries for whales; top-N by USD with
                                    filtering of spam/scam tokens, both sides
  /addresses/{a}/token-transfers -> recent transfer list
  /addresses/{a}/transactions    -> tx timestamps for dormancy
"""

from __future__ import annotations

from .client import blockscout, ApiError
from .chains import CHAINS

SPAM_SYMBOLS = {"", "FREE", "AIRDROP", "CLAIM", "REWARD", "GIFT"}


def _looks_spammy(symbol: str, name: str, amount: float, usd: float,
                  volume_24h: float = 0.0) -> bool:
    """Heuristics for airdropped spam/scam tokens that pollute reports:
    - giveaway vocabulary in symbol/name
    - quadrillion-scale amounts with negligible USD value
    - illiquid dust: the holding's claimed USD value exceeds 100x the token's
      ENTIRE daily volume — the value is unrealizable (classic scam-token
      pricing; the EF wallet's FOXE 'holding' is the live example)
    """
    text = f"{symbol} {name}".lower()
    if any(w in text for w in ("airdrop", "claim your", "giveaway")):
        return True
    if amount > 1e12 and usd < 100:
        return True
    if usd > 50 and volume_24h > 0 and usd > 100 * volume_24h:
        return True
    return False


def _num(x) -> float:
    try:
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _int(x) -> int:
    try:
        return int(x) if x is not None else 0
    except (TypeError, ValueError):
        return 0


def fetch_chain_snapshot(chain: str, address: str, top_tokens: int = 40) -> dict:
    """One chain's full snapshot for one address."""
    host = CHAINS[chain]["host"]
    info = blockscout(host, f"/addresses/{address}")

    native_raw = _int(info.get("coin_balance"))
    native_dec = CHAINS[chain]["decimals"]
    # native exchange_rate from Blockscout; fall back to CoinGecko later
    native_rate = _num(info.get("exchange_rate"))
    native = {
        "chain": chain,
        "symbol": CHAINS[chain]["native"],
        "balance": native_raw / 10 ** native_dec,
        "usd": (native_raw / 10 ** native_dec) * native_rate,
        "rate_source": "blockscout" if native_rate else "none",
    }

    tokens = []
    token_meta: dict[str, dict] = {}
    try:
        balances = blockscout(host, f"/addresses/{address}/token-balances")
    except ApiError as e:
        if e.status in (404, 400):
            balances = []
        else:
            raise
    for b in balances:
        tok = b.get("token") or {}
        if tok.get("type") != "ERC-20":
            continue
        rate = _num(tok.get("exchange_rate"))
        decimals = _int(tok.get("decimals")) or 18
        value_raw = _int(b.get("value"))
        if value_raw == 0:
            price_zero = rate > 0
            if not price_zero:
                continue
        rep = (tok.get("reputation") or "").lower()
        if rep == "scam":
            continue
        symbol = (tok.get("symbol") or "").strip()
        if symbol in SPAM_SYMBOLS and rate == 0:
            continue
        amount = value_raw / 10 ** decimals
        usd = amount * rate
        if _looks_spammy(symbol, tok.get("name") or "", amount, usd,
                         _num(tok.get("volume_24h"))):
            continue
        entry = {
            "chain": chain,
            "token_address": (tok.get("address_hash") or tok.get("address") or "").lower(),
            "symbol": symbol,
            "name": tok.get("name") or "",
            "amount": amount,
            "usd": usd,
            "rate": rate,
            "decimals": decimals,
        }
        tokens.append(entry)
        token_meta[entry["token_address"]] = {
            "symbol": symbol, "decimals": str(decimals), "rate": rate,
            "balance": amount,
        }
    tokens.sort(key=lambda t: t["usd"], reverse=True)
    tokens = tokens[:top_tokens]
    total_usd = native["usd"] + sum(t["usd"] for t in tokens)
    return {
        "chain": chain,
        "address": address,
        "ens": info.get("ens_domain_name"),
        "is_contract": bool(info.get("is_contract")),
        "proxy_type": info.get("proxy_type"),
        "is_scam": bool(info.get("is_scam")),
        "native": native,
        "tokens": tokens,
        "token_meta": token_meta,
        "total_usd": total_usd,
    }


def fetch_recent_activity(chain: str, address: str) -> dict:
    """Last known activity + tx counts for dormancy scoring."""
    host = CHAINS[chain]["host"]
    out: dict = {"chain": chain, "last_tx": None, "tx_count": 0, "inflow_30d": 0.0,
                 "outflow_30d": 0.0, "error": None}
    try:
        counters = blockscout(host, f"/addresses/{address}/counters")
        out["tx_count"] = _int(counters.get("transactions_count"))
    except ApiError:
        out["error"] = "counters"
    try:
        txs = blockscout(host, f"/addresses/{address}/transactions",
                        {"filter": "from"})
        items = txs.get("items", [])
        if items:
            out["last_tx"] = items[0].get("timestamp")
            # rough 30-day flows in native units
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            window = _dt.timedelta(days=30)
            for it in items:
                ts = it.get("timestamp")
                if not ts:
                    continue
                when = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if now - when > window:
                    break
                out["outflow_30d"] += _int(it.get("value")) / 10 ** CHAINS[chain]["decimals"]
    except (ApiError, KeyError):
        out["error"] = out["error"] or "transactions"
    return out
