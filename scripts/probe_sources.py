#!/usr/bin/env python3
"""Probe every data source the WalletRisk engine depends on. Read-only.

Answers, with evidence printed to stdout:
  1. eth_getLogs block-range limit on eth.blockscout.com's /api/eth-rpc proxy
  2. which chains have a working Blockscout v2 (with browser UA)
  3. whether any instance exposes /addresses/{h}/allowances
  4. token-balances endpoint reliability
  5. full allowance pipeline on a real wallet: getLogs -> eth_call allowance()
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
ALLOWANCE_SELECTOR = "0xdd62ed3e"  # allowance(address,address)

VITALIK = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def req(url, payload=None, timeout=60, redirects=True):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler() if redirects else _NoRedirect())
    with opener.open(r, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode() or "null")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def rpc(host, method, params, timeout=60):
    url = f"https://{host}/api/eth-rpc"
    try:
        _, d = req(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
        return d
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"error": str(e)[:200]}


print("=== A. latest block + getLogs range probes on eth.blockscout.com ===")
tip = rpc("eth.blockscout.com", "eth_blockNumber", ["latest"])
print("tip:", tip.get("result"))
tip_int = int(tip.get("result", "0x0"), 16)

owner_topic = "0x" + VITALIK.lower().replace("0x", "").rjust(64, "0")
for span in (5_000, 50_000, 500_000, 5_000_000):
    t0 = time.time()
    res = rpc("eth.blockscout.com", "eth_getLogs", [{
        "fromBlock": hex(tip_int - span), "toBlock": "latest",
        "topics": [APPROVAL_TOPIC, owner_topic],
    }], timeout=90)
    if "error" in res:
        print(f"span={span}: ERROR {res['error']} ({time.time()-t0:.1f}s)")
    else:
        n = len(res.get("result", []))
        print(f"span={span}: {n} logs ({time.time()-t0:.1f}s)")

print("\n=== B. per-chain blockscout v2 stats + allowances endpoint (browser UA) ===")
hosts = [
    ("ethereum", "eth.blockscout.com"), ("base", "base.blockscout.com"),
    ("polygon", "polygon.blockscout.com"), ("arbitrum", "arbitrum.blockscout.com"),
    ("optimism", "optimism.blockscout.com"), ("gnosis", "gnosis.blockscout.com"),
    ("zksync", "zksync.blockscout.com"), ("linea", "explorer.linea.build"),
    ("base-alt", "base.blockscout.com"),
]
for label, host in hosts:
    try:
        st, d = req(f"https://{host}/api/v2/stats", timeout=25)
        total = d.get("total_blocks") if isinstance(d, dict) else d
        print(f"{label:12} {host:28} v2 OK  total_blocks={str(total)[:12]}")
        try:
            st2, d2 = req(
                f"https://{host}/api/v2/addresses/{VITALIK}/allowances?token_type=erc-20",
                timeout=25)
            body = json.dumps(d2)[:150]
            print(f"{'':12} {'':28} allowances -> {st2} {body}")
        except urllib.error.HTTPError as e:
            print(f"{'':12} {'':28} allowances -> HTTP {e.code} {e.read().decode()[:80]}")
        except Exception as e:
            print(f"{'':12} {'':28} allowances -> ERR {str(e)[:80]}")
    except urllib.error.HTTPError as e:
        print(f"{label:12} {host:28} v2 HTTP {e.code}")
    except Exception as e:
        print(f"{label:12} {host:28} v2 ERR {str(e)[:80]}")

print("\n=== C. token-balances (retry, patient) ===")
t0 = time.time()
try:
    st, d = req(f"https://eth.blockscout.com/api/v2/addresses/{VITALIK}/token-balances", timeout=120)
    items = d if isinstance(d, list) else d.get("items", [])
    print(f"token-balances: {len(items)} entries ({time.time()-t0:.1f}s)")
    if items:
        print("first:", json.dumps(items[0])[:200])
except Exception as e:
    print(f"token-balances FAILED after {time.time()-t0:.1f}s: {str(e)[:150]}")

print("\n=== D. allowance() eth_call on a real vitalik approval ===")
res = rpc("eth.blockscout.com", "eth_getLogs", [{
    "fromBlock": hex(tip_int - 5_000_000), "toBlock": "latest",
    "topics": [APPROVAL_TOPIC, owner_topic],
}], timeout=90)
logs = res.get("result", [])
print(f"got {len(logs)} approval logs")
if logs:
    log = logs[-1]
    token = "0x" + log["address"][2:]
    spender = "0x" + log["topics"][2][-40:]
    # allowance(owner, spender) calldata
    calldata = (ALLOWANCE_SELECTOR + VITALIK.lower().replace("0x", "").rjust(64, "0")
                + spender.replace("0x", "").rjust(64, "0"))
    r2 = rpc("eth.blockscout.com", "eth_call", [{"to": token, "data": calldata}, "latest"])
    val = r2.get("result")
    print(f"token={token} spender={spender}")
    print(f"current allowance hex={val} -> int={int(val,16) if val and val!='0x' else 0}")
    # token metadata
    try:
        st, d = req(f"https://eth.blockscout.com/api/v2/tokens/{token}", timeout=25)
        print("token meta:", d.get("symbol"), d.get("name"), "decimals", d.get("decimals"))
    except Exception as e:
        print("token meta ERR", str(e)[:100])
    # spender contract info
    try:
        st, d = req(f"https://eth.blockscout.com/api/v2/addresses/{spender}", timeout=25)
        print("spender info:", json.dumps({k: d.get(k) for k in
              ("is_contract", "name", "is_verified", "proxy_type")})[:200])
    except Exception as e:
        print("spender info ERR", str(e)[:100])
