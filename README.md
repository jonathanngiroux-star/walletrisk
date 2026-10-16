# WalletRisk

**Free, keyless, read-only wallet approval scanner.** Finds the token
approvals you forgot you gave — live UNLIMITED allowances, dormant traps,
NFT blanket approvals — across six EVM chains, using only public data.

- **Web app (no backend):** `web/index.html` — runs entirely in your
  browser, querying public Blockscout instances and publicnode RPCs
  directly (both are CORS-open). Nothing is stored, nothing is logged.
- **Python CLI / engine:** same pipeline, for batch scans and reports.
  Stdlib only, zero dependencies.

```
python3 -m walletrisk 0xf39b9FFAC0FbC5Ab3b9C04a729c27053e407E640 --chain ethereum
python3 -m walletrisk vitalik.eth          # ENS works
python3 -m walletrisk 0x... --json         # machine-readable
```

## How it works (honesty-first)

1. **Discovery** — your current holdings and the contracts you've
   interacted with are read from public Blockscout v2 instances, plus a
   curated registry of major spenders (Uniswap routers, Permit2, 1inch,
   OpenSea, Aave).
2. **Live checks** — every candidate (token × spender) pair is verified
   with a live `allowance()` / `isApprovedForAll()` `eth_call` via
   publicnode public RPC. Stale or revoked approvals show zero and are
   never reported. Only chain truth, no heuristics.
3. **Risk model** — UNLIMITED approvals on tokens you hold = HIGH;
   unlimited on zero-balance tokens = MEDIUM (dormant trap); small live
   allowances = LOW.
4. **You revoke** — every finding links to revoke.cash, where **you**
   sign the revoke with your own wallet. WalletRisk never asks for keys
   and never broadcasts anything.

## Chains

Ethereum · Base · Polygon · Arbitrum · Optimism · Gnosis

(BSC / Linea / Avalanche are absent because there is no usable keyless
explorer API for them today; we prefer honest coverage over checkbox
count. Publicnode CORS serves all six listed chains.)

## Paid tier — Pro reports & monitoring

The free scan is the product. Pro ($9/mo, $89/yr, crypto) adds scheduled
multi-chain re-scans, email alerts when new approvals appear, and deep
reports covering full interaction history.

**How to order:** send payment to one of the addresses below, then email
**wallethygiene@agentmail.to** with (1) your wallet address, (2) the
transaction hash, (3) your delivery email. The payment is verified
on-chain, then your report is delivered by email. No accounts.

| Asset | Address |
|-------|---------|
| USDC / any EVM token (ETH, Base, Polygon, Arbitrum, Optimism, Gnosis, BNB, Linea, Monad, Arc) | `0x85ee7E71f762d772599cbF1EC20E651B30657521` |
| BTC | `bc1qxe2zx5tv3hdreaej6s2x4p7han85uey828rrhg` |
| SOL | `4afnnpah1KYUF5T6mCfkdSo9guWcLQGvoEDnpqNZzfTw` |
| TRX | `TCJMp9eMGDzSM8bDCPB7QDz3KxqiuvBrW9` |
| XLM | `GDKGPEO7CC46IRV7EUUWMITA3VA4447OZTFLGXDVXEZPV7VB3F5M7VA4` |

Orders and payment verification are handled by the WalletHygiene agent;
see `scripts/verify_payment.py` for the on-chain verification logic (also
keyless and read-only).

## Examples

See `examples/` for real scans of real wallets — including wallets with
live UNLIMITED approvals the free scanner found (grade F), and clean
controls (grade A).

## Disclaimers

Informational only, not financial advice. Discovery windows cover recent
history (~200 txs) plus curated majors; approvals granted via Permit2
signatures or contracts you interacted with long ago may not surface —
revoke.cash remains the authoritative full list. Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).
