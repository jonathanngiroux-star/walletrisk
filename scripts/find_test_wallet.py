#!/usr/bin/env python3
"""Find a test wallet with a KNOWN live approval, to validate the scanner
detects real findings (negative-control: wallets above showed none)."""
import json
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
UNIV3 = "0xe592427a0aece92de3edee1f18e0157c05861564"
UNIV2 = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
INFINITE = 1 << 255


def bs(path):
    req = urllib.request.Request(f"https://eth.blockscout.com/api/v2{path}",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def rpc_call(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    req = urllib.request.Request("https://ethereum-rpc.publicnode.com", data=payload,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def allowance(token, owner, spender):
    data = ("0xdd62ed3e" + owner.lower()[2:].rjust(64, "0")
            + spender.lower()[2:].rjust(64, "0"))
    d = rpc_call("eth_call", [{"to": token, "data": data}, "latest"])
    v = d.get("result", "0x")
    return int(v, 16) if v and v != "0x" else 0


CANDIDATES = [
    "0x42da18585662b1d20fB14573148669f3674Fb290",
    "0xF22CbcE1bB0BF632381861Fa578c8F99046b4c9a",
    "0xab300e6A316eeE07b4D6A114E875BFE28f0b107b",
    "0xf39b9FFAC0FbC5Ab3b9C04a729c27053e407E640",
    "0xCa2959aCb2D811acFAF12562E299ba7eE4240382",
    "0x54D6aeB5BdBecA6C908e9d4d979F6b5F17B2B21d",
    "0x297e8E268A79e07d91764d046085a814030a71Ad",
    "0xb43C1981d57161Dcb077Ee4BcBB2d376b577a857",
    "0xA51c714Ad8d573fDa76E3613B690a0b773b3965f",
    "0x54bD6b31cf0C087fe3cD5d30c40BaF5b3D66647C",
    "0xe9513b9553bfc876F36BeA6416792c5A8451633E",
]

for w in CANDIDATES:
    try:
        toks = bs(f"/addresses/{w}/tokens").get("items", [])
        hits = []
        for t in toks[:10]:
            addr = (t.get("token") or {}).get("address_hash")
            if not addr:
                continue
            for spender, name in ((UNIV3, "UniV3"), (UNIV2, "UniV2")):
                v = allowance(addr, w, spender)
                if v > 0:
                    hits.append((t["token"].get("symbol"), name, v, v >= INFINITE))
        if hits:
            print(f"{w}")
            for h in hits:
                print(f"   {h[0]} -> {h[1]}: {h[2]} {'INFINITE' if h[3] else ''}")
        else:
            print(f"{w}  (no live approvals to Uni routers)")
    except Exception as e:
        print(f"{w}  ERR {str(e)[:60]}")
