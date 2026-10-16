#!/usr/bin/env python3
"""Probe round 3: does Blockscout v2 /logs topic filtering actually work?
Plus alternative archive RPCs for full-history approval discovery."""
import json
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
APPROVAL = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def post(url, payload, timeout=60, origin=None):
    h = {"Content-Type": "application/json", "User-Agent": UA}
    if origin:
        h["Origin"] = origin
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            acao = r.headers.get("access-control-allow-origin")
            return json.loads(r.read().decode()), acao
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}, None
    except Exception as e:
        return {"error": str(e)[:150]}, None


print("=== 1. /logs?topic0 only (global Approvals, newest first) ===")
try:
    st, d = get(f"https://eth.blockscout.com/api/v2/logs?topic0={APPROVAL}")
    items = d.get("items", [])
    print(f"items={len(items)} next={d.get('next_page_params')}")
    if items:
        print("first log:", json.dumps({k: items[0].get(k) for k in ("address", "block_number", "topics", "index")})[:400])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:150])

print("\n=== 2. /logs?address=USDT&topic0=Approval ===")
try:
    st, d = get(f"https://eth.blockscout.com/api/v2/logs?address={USDT}&topic0={APPROVAL}")
    items = d.get("items", [])
    print(f"items={len(items)}")
    if items:
        lg = items[0]
        print("first:", json.dumps({k: lg.get(k) for k in ("topics", "block_number", "tx_hash")})[:300])
        # now take this owner and test combined filter
        owner_topic = lg["topics"][1]
        print("\n=== 3. combined topic0+topic1 with real owner ===")
        st2, d2 = get(f"https://eth.blockscout.com/api/v2/logs?topic0={APPROVAL}&topic1={owner_topic}&topic0_1_opr=and")
        items2 = d2.get("items", [])
        print(f"items={len(items2)} next={d2.get('next_page_params')}")
        if items2:
            print("first:", json.dumps({k: items2[0].get(k) for k in ("address", "block_number")})[:200])
            # verify the spender field decodes
            print("spender from topics[2]:", "0x" + items2[0]["topics"][2][-40:])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:150])

print("\n=== 4. alternative public archive RPCs: full-history getLogs ===")
V = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
OWNER = "0x" + V.lower()[2:].rjust(64, "0")
gl_params = [{"fromBlock": "0x0", "toBlock": "latest", "topics": [APPROVAL, OWNER]}]
for name, url in [
    ("llamarpc", "https://eth.llamarpc.com"),
    ("drpc", "https://eth.drpc.org"),
    ("flashbots", "https://rpc.flashbots.net"),
    ("merkle", "https://eth.merkle.io"),
    ("mevblocker", "https://rpc.mevblocker.io"),
    ("alchemy-demo", "https://eth-mainnet.g.alchemy.com/v2/demo"),
    ("ankr-pub", "https://rpc.ankr.com/eth"),
    ("1rpc", "https://1rpc.io/eth"),
]:
    d, _ = post(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": gl_params}, timeout=45)
    if "error" in d:
        print(f"{name:14} ERR {str(d['error'])[:120]}")
    else:
        print(f"{name:14} OK {len(d.get('result', []))} logs")

print("\n=== 5. same RPCs: eth_call allowance() (vitalik -> USDT -> Uniswap V2 router) ===")
ROUTER2 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
cd = ("0xdd62ed3e" + V.lower()[2:].rjust(64, "0") + ROUTER2.lower()[2:].rjust(64, "0"))
for name, url in [
    ("llamarpc", "https://eth.llamarpc.com"),
    ("drpc", "https://eth.drpc.org"),
    ("flashbots", "https://rpc.flashbots.net"),
]:
    d, acao = post(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                         "params": [{"to": USDT, "data": cd}, "latest"]}, timeout=30,
                    origin="https://katsironni.github.io")
    if "error" in d:
        print(f"{name:14} ERR {str(d['error'])[:100]} ACAO={acao!r}")
    else:
        val = d.get("result", "0x")
        print(f"{name:14} allowance={int(val, 16) if val and val != '0x' else 0} ACAO={acao!r}")
