#!/usr/bin/env python3
"""Probe round 4 — verify the exact keyless pipeline:
  A. publicnode eth_call allowance(owner, spender) [live value, CORS]
  B. Blockscout /addresses/{h}/transactions -> 'to' contracts (interaction set)
  C. Blockscout /addresses/{h}/tokens -> current holdings w/ prices
  D. ApprovalForAll via eth_call isApprovedForAll
  E. put together: does (B x C x A) find real approvals for vitalik?
"""
import json
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
V = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
VLOW = V.lower()
OWNER_PAD = VLOW[2:].rjust(64, "0")
USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ROUTER2 = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
PERMIT2 = "0x000000000022d473030f116ddee9f6b158459460"
UNIV3ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"


def post_rpc(url, method, params, origin=None, timeout=30):
    h = {"Content-Type": "application/json", "User-Agent": UA}
    if origin:
        h["Origin"] = origin
    req = urllib.request.Request(url, data=json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()), r.headers.get("access-control-allow-origin")


def get_bs(host, path, timeout=40):
    req = urllib.request.Request(f"https://{host}/api/v2{path}",
                                headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()), r.headers.get("access-control-allow-origin")


print("=== A. allowance() via publicnode (CORS) ===")
for tok, spender, label in [
    (USDT, ROUTER2, "USDT -> UniV2 Router"),
    (USDC, PERMIT2, "USDC -> Permit2"),
    (USDC, UNIV3ROUTER, "USDC -> UniV3 Router"),
]:
    cd = "0xdd62ed3e" + OWNER_PAD + spender.lower()[2:].rjust(64, "0")
    d, acao = post_rpc("https://ethereum-rpc.publicnode.com", "eth_call",
                       [{"to": tok, "data": cd}, "latest"], origin="https://katsironni.github.io")
    val = d.get("result", "0x")
    n = int(val, 16) if val and val != "0x" else 0
    print(f"{label:22} = {n} ({'UNLIMITED' if n >= 2**255 else 'zero/limited'})  ACAO={acao!r}")

print("\n=== B. interaction set: /addresses/vitalik/transactions ===")
d, acao = get_bs("eth.blockscout.com", f"/addresses/{V}/transactions")
items = d.get("items", [])
tos = {}
for it in items:
    to = (it.get("to") or {}).get("hash")
    if to:
        tos[to.lower()] = tos.get(to.lower(), 0) + 1
print(f"page1: {len(items)} txs, ACAO={acao!r}, next={d.get('next_page_params') is not None}")
print("interacted-with (to):")
for a, c in sorted(tos.items(), key=lambda x: -x[1])[:10]:
    print(f"   {a} x{c}")

print("\n=== C. holdings: /addresses/vitalik/tokens (valuable first) ===")
d2, _ = get_bs("eth.blockscout.com", f"/addresses/{V}/tokens")
toks = d2.get("items", [])
print(f"page1: {len(toks)} tokens")
for t in toks[:5]:
    tok = t.get("token", {})
    print(f"   {tok.get('symbol','?'):8} {t.get('value')}  usd={t.get('token',{}).get('exchange_rate')}")
print("next_page_params:", d2.get("next_page_params"))

print("\n=== D. isApprovedForAll via publicnode (BAYC, vitalik -> OpenSea Seaport?) ===")
# OpenSea Seaport conduit address on mainnet:
OPENSEA = "0x00000000000000681160bd39558242511370d223"  # deprecated OpenSea wyvern proxy
BAYC = "0xBC4CA0EdA7642748d03671eB2fB18e2a5E6cDd13"     # BAYC NFT contract
for nft, op, label in [(BAYC, OPENSEA, "BAYC -> OpenSea legacy conduit")]:
    cd = ("0xe985e9c5" + OWNER_PAD + op.lower()[2:].rjust(64, "0"))  # isApprovedForAll(address,address)
    d, acao = post_rpc("https://ethereum-rpc.publicnode.com", "eth_call",
                       [{"to": nft, "data": cd}, "latest"], origin="https://katsironni.github.io")
    val = d.get("result", "0x")
    n = int(val, 16) if val and val != "0x" else 0
    print(f"{label:36} = {n} ({'APPROVED FOR ALL' if n == 1 else 'not approved'})  ACAO={acao!r}")

print("\n=== E. combined: allowance for every (token, spender) from B x C ===")
# take top-5 tokens from C and every 'to' from B, query allowance for each pair
spend_whitelist = {ROUTER2.lower(), PERMIT2.lower(), UNIV3ROUTER.lower()}
spenders = set(tos.keys()) | spend_whitelist
tokens = {}
for t in toks:
    tok = t.get("token", {})
    addr = tok.get("address_hash") or tok.get("address")
    if addr:
        tokens[addr.lower()] = tok.get("symbol", "?")
pairs = 0
found = 0
for taddr, sym in list(tokens.items())[:6]:
    for saddr in list(spenders)[:12]:
        cd = "0xdd62ed3e" + OWNER_PAD + saddr[2:].rjust(64, "0")
        try:
            d, _ = post_rpc("https://ethereum-rpc.publicnode.com", "eth_call",
                            [{"to": taddr, "data": cd}, "latest"], timeout=20)
        except Exception as e:
            continue
        pairs += 1
        val = d.get("result", "0x")
        n = int(val, 16) if val and val != "0x" else 0
        if n > 0:
            found += 1
            print(f"   LIVE APPROVAL: {sym} -> {saddr} = {n} {'UNLIMITED' if n >= 2**255 else ''}")
        time.sleep(0.05)
print(f"checked {pairs} pairs, found {found} live approvals")
