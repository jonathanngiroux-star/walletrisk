#!/usr/bin/env python3
"""Probe round 2: publicnode RPC viability (CORS + getLogs ranges), Blockscout
light endpoints, and payment-verification endpoints. Read-only."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
APPROVAL = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
FORALL = "0x17307eab39ab6107e8899845ad3d59bd9653f200a25e1d5eabd3ff0b1c9f4b9d"
V = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
OWNER = "0x" + V.lower()[2:].rjust(64, "0")
PAY = "0x85ee7E71f762d772599cbF1EC20E651B30657521"
PAY_T = "0x" + PAY.lower()[2:].rjust(64, "0")
USDC_ETH = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

RPCS = {
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "base": "https://base-rpc.publicnode.com",
    "polygon": "https://polygon-bor-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
    "optimism": "https://optimism-rpc.publicnode.com",
    "gnosis": "https://gnosis-rpc.publicnode.com",
    "zksync": "https://zksync-rpc.publicnode.com",
    "bnb": "https://bsc-rpc.publicnode.com",
    "linea": "https://linea-rpc.publicnode.com",
    "avalanche": "https://avalanche-c-chain-rpc.publicnode.com",
}


def rpc(url, method, params, timeout=60, cors=False):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if cors:
        headers["Origin"] = "https://katsironni.github.io"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            acao = r.headers.get("access-control-allow-origin")
            return json.loads(r.read().decode()), acao
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:160]}"}, None
    except Exception as e:
        return {"error": str(e)[:160]}, None


print("=== 1. publicnode CORS headers (Origin: github.io) ===")
for name, url in RPCS.items():
    d, acao = rpc(url, "eth_blockNumber", ["latest"], timeout=20, cors=True)
    tip = d.get("result")
    print(f"{name:10} tip={'OK' if tip else d.get('error','?')[:40]}  ACAO={acao!r}")

print("\n=== 2. full-history getLogs range limits (Approval, vitalik topic1) ===")
for name in ("ethereum", "base", "polygon", "arbitrum", "optimism"):
    url = RPCS[name]
    d, _ = rpc(url, "eth_getLogs", [{
        "fromBlock": "0x0", "toBlock": "latest",
        "topics": [APPROVAL, OWNER],
    }], timeout=120)
    if "error" in d:
        print(f"{name:10} full-range: ERR {str(d['error'])[:130]}")
        # retry with 1M blocks
        tipd, _ = rpc(url, "eth_blockNumber", ["latest"], timeout=20)
        tip = int(tipd.get("result", "0x0"), 16)
        d, _ = rpc(url, "eth_getLogs", [{
            "fromBlock": hex(max(0, tip - 1_000_000)), "toBlock": "latest",
            "topics": [APPROVAL, OWNER],
        }], timeout=120)
        if "error" in d:
            print(f"{name:10} 1M-range : ERR {str(d['error'])[:130]}")
        else:
            print(f"{name:10} 1M-range : {len(d.get('result', []))} logs")
    else:
        print(f"{name:10} full-range: {len(d.get('result', []))} logs")

print("\n=== 3. ApprovalForAll full-range (ethereum) ===")
d, _ = rpc(RPCS["ethereum"], "eth_getLogs", [{
    "fromBlock": "0x0", "toBlock": "latest",
    "topics": [FORALL, OWNER],
}], timeout=120)
print("forAll:", f"{len(d.get('result', []))} logs" if "error" not in d else d["error"][:120])

print("\n=== 4. eth_call allowance() via publicnode ===")
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
# find a vitalik->X approval from step-2 logs to know a real spender
d, _ = rpc(RPCS["ethereum"], "eth_getLogs", [{
    "fromBlock": "0x0", "toBlock": "latest",
    "topics": [APPROVAL, OWNER],
}], timeout=120)
logs = d.get("result", [])
if logs:
    lg = logs[-1]
    token = lg["address"]
    spender = "0x" + lg["topics"][2][-40:]
    calldata = "0xdd62ed3e" + OWNER[2:] + lg["topics"][2][2:]
    d2, acao = rpc(RPCS["ethereum"], "eth_call", [{"to": token, "data": calldata}, "latest"],
                   timeout=30, cors=True)
    val = d2.get("result", "?")
    print(f"token={token} spender={spender} allowance={val} ACAO={acao!r}")
    if val and val != "0x":
        print(f"  -> {int(val, 16)}")
else:
    print("no logs to test with")

print("\n=== 5. blockscout light endpoints ===")
def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        acao = r.headers.get("access-control-allow-origin")
        return json.loads(r.read().decode()), acao

for label, url in [
    ("tokens (vitalik)", f"https://eth.blockscout.com/api/v2/addresses/{V}/tokens"),
    ("token-transfers (vitalik)", f"https://eth.blockscout.com/api/v2/addresses/{V}/token-transfers"),
    ("logs?topic (vitalik)", f"https://eth.blockscout.com/api/v2/addresses/{V}/logs?topic={APPROVAL}"),
    ("addr info (USDT contract)", f"https://eth.blockscout.com/api/v2/addresses/{USDT}"),
    ("token price USDC", f"https://eth.blockscout.com/api/v2/tokens/{USDC_ETH}"),
    ("block meta tip-100", "https://eth.blockscout.com/api/v2/blocks/26205700"),
]:
    try:
        d, acao = get(url)
        if isinstance(d, dict) and "items" in d:
            print(f"{label:28} items={len(d['items'])} next={bool(d.get('next_page_params'))} ACAO={acao!r}")
            if d["items"]:
                print("   first:", json.dumps(d["items"][0])[:180])
        else:
            keys = list(d.keys())[:8] if isinstance(d, dict) else type(d)
            print(f"{label:28} keys={keys} ACAO={acao!r}")
    except Exception as e:
        print(f"{label:28} ERR {str(e)[:100]}")

print("\n=== 6. payment verification endpoints (payment address) ===")
# native txs on eth + token transfers on base
for label, url in [
    ("eth native txs", f"https://eth.blockscout.com/api/v2/addresses/{PAY}/transactions"),
    ("eth token transfers", f"https://eth.blockscout.com/api/v2/addresses/{PAY}/token-transfers"),
    ("base token transfers", f"https://base.blockscout.com/api/v2/addresses/{PAY}/token-transfers"),
]:
    try:
        d, _ = get(url)
        items = d.get("items", [])
        print(f"{label:22} items={len(items)} next={bool(d.get('next_page_params'))}")
        for it in items[:2]:
            print("   ", json.dumps({k: it.get(k) for k in ("hash", "value", "token", "total", "timestamp", "from", "to")})[:220])
    except Exception as e:
        print(f"{label:22} ERR {str(e)[:100]}")

# BTC via blockstream
print("\n=== 7. BTC address history (blockstream) ===")
try:
    req = urllib.request.Request("https://blockstream.info/api/address/bc1qxe2zx5tv3hdreaej6s2x4p7han85uey828rrhg/txs",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        acao = r.headers.get("access-control-allow-origin")
        txs = json.loads(r.read().decode())
        print(f"btc txs: {len(txs)}  ACAO={acao!r}")
except urllib.error.HTTPError as e:
    print(f"btc txs: HTTP {e.code} {e.read().decode()[:80]}")
except Exception as e:
    print(f"btc txs ERR: {str(e)[:80]}")

print("\n=== 8. Solana getSignaturesForAddress (CORS) ===")
payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                      "params": ["4afnnpah1KYUF5T6mCfkdSo9guWcLQGvoEDnpqNZzfTw", {"limit": 5}]}).encode()
req = urllib.request.Request("https://api.mainnet-beta.solana.com", data=payload,
                             headers={"Content-Type": "application/json", "User-Agent": UA,
                                      "Origin": "https://katsironni.github.io"})
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        acao = r.headers.get("access-control-allow-origin")
        d = json.loads(r.read().decode())
        print(f"solana sigs: {len(d.get('result', []))}  ACAO={acao!r}")
except urllib.error.HTTPError as e:
    print(f"solana: HTTP {e.code} {e.read().decode()[:80]}")
except Exception as e:
    print(f"solana ERR {str(e)[:80]}")
