# WalletRisk report — `0xd8da6bf26964af9d7eed9e03e53415d37aa96045` (vitalik.eth)

**Scanned:** 2026-10-16T19:05:23Z  
**Grade: F** — 1 unlimited approval(s) actively exposed — revoke now.

- [Ethereum] Revoke WHITE allowance to 1inch: Aggregation Router v5… — unlimited, holding $334,700.

## Ethereum

- Native balance: 5.7697 ETH
- Last activity: 2026-10-16T17:45:11.000000Z
- Holdings checked: 40 tokens
- Findings: **1 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/ethereum

| Sev | Token | Spender | Exposure | Why |
|-----|-------|---------|----------|-----|
| HIGH | WHITE | 1inch: Aggregation Router v5 | $334,700 | UNLIMITED approval while holding $334,700 of WHITE. |

## Method & disclaimers

- Only live, on-chain approvals are reported — verified via eth_call at scan time.
- Discovery covers curated majors + your wallet's own transaction history (last ~200 txs + recent transfers).
- Approvals granted via Permit2/off-chain signatures are not visible as allowances; monitor regularly.
- Not financial advice. Read-only tool; we never request keys or sign anything.