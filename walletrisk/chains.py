"""Chain registry: live Blockscout v2 instances (browser UA required) for
discovery + publicnode public RPCs for live allowance eth_calls.
Verified live 2026-10-16: all hosts answer /api/v2 and eth_call with ACAO:*.
zksync publicnode 404s; BSC/Linea/Avax have no usable keyless explorer —
registry-only discovery would give a false sense of coverage, so they are
NOT offered (v1 honesty over checkbox count)."""

from __future__ import annotations

CHAINS: dict[str, dict] = {
    "ethereum": {
        "host": "eth.blockscout.com", "rpc": "https://ethereum-rpc.publicnode.com",
        "native": "ETH", "decimals": 18, "cg_id": "ethereum", "label": "Ethereum",
        "revoke_slug": "ethereum", "explorer": "https://etherscan.io",
    },
    "base": {
        "host": "base.blockscout.com", "rpc": "https://base-rpc.publicnode.com",
        "native": "ETH", "decimals": 18, "cg_id": "ethereum", "label": "Base",
        "revoke_slug": "base", "explorer": "https://basescan.org",
    },
    "polygon": {
        "host": "polygon.blockscout.com", "rpc": "https://polygon-bor-rpc.publicnode.com",
        "native": "POL", "decimals": 18, "cg_id": "polygon-ecosystem-token", "label": "Polygon",
        "revoke_slug": "polygon", "explorer": "https://polygonscan.com",
    },
    "arbitrum": {
        "host": "arbitrum.blockscout.com", "rpc": "https://arbitrum-one-rpc.publicnode.com",
        "native": "ETH", "decimals": 18, "cg_id": "ethereum", "label": "Arbitrum",
        "revoke_slug": "arbitrum", "explorer": "https://arbiscan.io",
    },
    "optimism": {
        "host": "optimism.blockscout.com", "rpc": "https://optimism-rpc.publicnode.com",
        "native": "ETH", "decimals": 18, "cg_id": "ethereum", "label": "Optimism",
        "revoke_slug": "optimism", "explorer": "https://optimistic.etherscan.io",
    },
    "gnosis": {
        "host": "gnosis.blockscout.com", "rpc": "https://gnosis-rpc.publicnode.com",
        "native": "xDAI", "decimals": 18, "cg_id": "xdai", "label": "Gnosis",
        "revoke_slug": "gnosis", "explorer": "https://gnosisscan.io",
    },
}

DEFAULT_CHAINS = list(CHAINS)


def host_of(chain: str) -> str:
    if chain not in CHAINS:
        raise KeyError(f"unsupported chain {chain!r}; known: {sorted(CHAINS)}")
    return CHAINS[chain]["host"]


def rpc_of(chain: str) -> str:
    return CHAINS[chain]["rpc"]
