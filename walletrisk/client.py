"""HTTP client for free public APIs — Blockscout v2, Blockscout eth-rpc proxy,
CoinGecko, ENS. Stdlib only, throttled, retried, browser-UA (Blockscout 403s
non-browser UAs). All read-only."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"


class RateLimitError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url}: {body[:200]}")
        self.status = status
        self.body = body
        self.url = url


class Throttle:
    """Per-host min-interval throttle (Blockscout free tier 429s under load)."""

    def __init__(self):
        self._last: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def wait(self, host: str, min_interval: float) -> None:
        with self._lock:
            now = time.monotonic()
            delta = self._last[host] + min_interval - now
            if delta > 0:
                time.sleep(delta)
            self._last[host] = time.monotonic()


_throttle = Throttle()
_host_interval: dict[str, float] = defaultdict(lambda: 0.6)
# strictest instance (free tier rate-limits eth hard):
_host_interval["eth.blockscout.com"] = 0.8


def set_host_interval(host: str, seconds: float) -> None:
    _host_interval[host] = seconds


def _fetch(method: str, url: str, payload: dict | None, timeout: int,
           retries: int) -> tuple[int, object]:
    host = urllib.request.urlparse(url).netloc
    for attempt in range(retries + 1):
        _throttle.wait(host, _host_interval[host])
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode()
                return r.status, json.loads(body) if body else None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:500]
            except Exception:
                pass
            if e.code == 429:
                if attempt < retries:
                    time.sleep(3 * (attempt + 1) + 2)
                    continue
                raise RateLimitError(url)
            if 500 <= e.code < 504 and attempt < retries:
                time.sleep(1 + attempt)
                continue
            raise ApiError(e.code, body, url)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise ApiError(0, str(e), url)
    raise ApiError(0, "unreachable", url)


def get_json(url: str, timeout: int = 30, retries: int = 2):
    _, data = _fetch("GET", url, None, timeout, retries)
    return data


def post_json(url: str, payload: dict, timeout: int = 45, retries: int = 2):
    _, data = _fetch("POST", url, payload, timeout, retries)
    return data


# --- typed helpers -----------------------------------------------------------

def blockscout(chain_host: str, path: str, params: dict | None = None) -> dict:
    url = f"https://{chain_host}/api/v2{path}"
    if params:
        from urllib.parse import urlencode
        # Blockscout's next_page_params can carry JSON nulls (e.g.
        # fiat_value=None); urlencode would render them as the literal string
        # "None", which the API 422s on. Drop them — they are optional filters.
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)
    return get_json(url)


def rpc_call(chain_host: str, method: str, params: list) -> dict:
    """Single JSON-RPC via Blockscout's /api/eth-rpc proxy."""
    return post_json(
        f"https://{chain_host}/api/eth-rpc",
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


def rpc_url_call(url: str, method: str, params: list) -> dict:
    """Single JSON-RPC against any endpoint URL (e.g. a publicnode RPC)."""
    return post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params})


def rpc_call_batch(chain_host: str, calls: list[dict]) -> list[dict]:
    """Batched JSON-RPC (one POST): calls = [{"method":..., "params":[...]}]."""
    return post_json(
        f"https://{chain_host}/api/eth-rpc",
        [{"jsonrpc": "2.0", "id": i, "method": c["method"], "params": c["params"]}
         for i, c in enumerate(calls)],
    )


# free mainnet RPC for full-history logs + batched allowance checks
# (Blockscout eth-rpc is capped ~10/min; mevblocker has no such cap)
MAINNET_RPC = "https://rpc.mevblocker.io"


def rpc_mainnet(method: str, params: list) -> dict:
    return post_json(MAINNET_RPC,
                     {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def rpc_mainnet_batch(calls: list[dict]) -> list[dict]:
    return post_json(MAINNET_RPC,
                     [{"jsonrpc": "2.0", "id": i, "method": c["method"], "params": c["params"]}
                      for i, c in enumerate(calls)])


def coingecko_simple(ids: list[str], vs: str = "usd") -> dict:
    from urllib.parse import quote
    return get_json(
        "https://api.coingecko.com/api/v3/simple/price?ids="
        + quote(",".join(ids)) + "&vs_currencies=" + vs
    )


def resolve_ens(name: str) -> str:
    """ENS -> address via Blockscout search (type=ens_domain → ens_info.address_hash)."""
    res = get_json("https://eth.blockscout.com/api/v2/search?q=" + urllib.parse.quote(name),
                   timeout=20, retries=2)
    for item in res.get("items", []):
        if item.get("type") == "ens_domain":
            ens = item.get("ens_info") or {}
            addr = ens.get("address_hash") or item.get("address")
            if addr:
                return addr.lower()
        # older shape: address items named after the ENS
        if item.get("type") == "address" and item.get("ens_info"):
            ens = item.get("ens_info") or {}
            if (ens.get("name") or "").lower() == name.lower() and ens.get("address"):
                return ens["address"].lower()
    raise ApiError(0, f"could not resolve ENS name {name!r}", "ens")
