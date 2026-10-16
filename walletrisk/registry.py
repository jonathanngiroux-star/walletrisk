"""Curated high-confidence spender registry. Every entry is RE-VERIFIED at
scan time via Blockscout /addresses/{h} (is_contract + reported name), so a
stale entry degrades to "unknown contract" instead of mislabeling.
The wallet's own interaction history supplies the long tail; this registry
only guarantees the majors are checked even for brand-new wallets."""

from __future__ import annotations

# name -> (chains, address)  (chapters: None = all supported chains)
_SPENDERS: list[tuple[str, list[str] | None, str]] = [
    ("Uniswap: Permit2", None, "0x000000000022d473030f116ddee9f6b158459460"),
    ("Uniswap V2: Router 02", ["ethereum"], "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"),
    ("Uniswap V3: SwapRouter", ["ethereum", "arbitrum", "optimism", "polygon"],
     "0xe592427a0aece92de3edee1f18e0157c05861564"),
    ("Uniswap: Universal Router",
     ["ethereum", "arbitrum", "optimism", "base", "polygon"],
     "0x3fc91a3afd70395cd496c647d5a6e9c314787c0f"),
    ("1inch: Aggregation Router v5", ["ethereum", "arbitrum", "optimism", "base", "polygon"],
     "0x111111125421ca6dc452d289314280a0f8842a65"),
    ("OpenSea: Seaport marketplace", ["ethereum", "arbitrum", "optimism", "base"],
     "0x00000000006c3852cbef3e08e8df289169dee586"),
    ("Aave V3: Pool", ["ethereum"], "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"),
]

# NFT marketplace candidates for isApprovedForAll (checked against every
# ERC-721/1155 holding + these registry entries).
_NFT_HUBS: list[tuple[str, list[str] | None, str]] = [
    ("OpenSea: Seaport marketplace", ["ethereum", "arbitrum", "optimism", "base"],
     "0x00000000006c3852cbef3e08e8df289169dee586"),
]


def spenders_for(chain: str) -> list[dict]:
    out = []
    for name, chains, addr in _SPENDERS:
        if chains is None or chain in chains:
            out.append({"address": addr.lower(), "registry_name": name})
    return out


def nft_hubs_for(chain: str) -> list[dict]:
    out = []
    for name, chains, addr in _NFT_HUBS:
        if chains is None or chain in chains:
            out.append({"address": addr.lower(), "registry_name": name})
    return out
