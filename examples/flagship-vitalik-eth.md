# WalletRisk report — `0xd8da6bf26964af9d7eed9e03e53415d37aa96045` (vitalik.eth)

**Scanned:** 2026-10-16T17:06:44Z  
**Grade: F** — 1 unlimited approval(s) actively exposed — revoke now.

- [Ethereum] Revoke WHITE allowance to 1inch: Aggregation Router v5… — unlimited, holding $335,600.

## Ethereum

- Native balance: 5.7697 ETH
- Last activity: 2026-10-13T07:25:11.000000Z
- Holdings checked: 40 tokens
- Findings: **1 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/ethereum

| Sev | Token | Spender | Exposure | Why |
|-----|-------|---------|----------|-----|
| HIGH | WHITE | 1inch: Aggregation Router v5 | $335,600 | UNLIMITED approval while holding $335,600 of WHITE. |

## Base

- Native balance: 3.1288 ETH
- Last activity: 2026-09-29T18:17:57.000000Z
- Holdings checked: 40 tokens
- Findings: **0 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/base

## Polygon

- Native balance: 592.7198 POL
- Last activity: 2026-09-30T19:15:09.000000Z
- Holdings checked: 40 tokens
- Findings: **0 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/polygon

## Arbitrum

- Native balance: 0.1594 ETH
- Last activity: 2026-10-16T11:09:27.000000Z
- Holdings checked: 40 tokens
- Findings: **0 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/arbitrum

## Optimism

- Native balance: 0.1811 ETH
- Last activity: 2026-09-30T02:38:35.000000Z
- Holdings checked: 40 tokens
- Findings: **0 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/optimism

## Gnosis

- Native balance: 8.7095 xDAI
- Last activity: 2026-05-19T00:37:50.000000Z
- Holdings checked: 40 tokens
- Findings: **0 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xd8da6bf26964af9d7eed9e03e53415d37aa96045/gnosis

> **Flagship scan** — vitalik.eth, the most-scanned wallet on Ethereum, verified independently via direct `eth_call`.
> **Liquidity caveat:** the $335,600 figure is quoted rate × holdings. WHITE is an illiquid token; the realizable value of dumping 10B tokens would be far lower. The *approval* being unlimited is the finding — it costs nothing to revoke.

## Method & disclaimers

- Only live, on-chain approvals are reported — verified via eth_call at scan time.
- Discovery covers curated majors + your wallet's own transaction history (last ~200 txs + recent transfers).
- Approvals granted via Permit2/off-chain signatures are not visible as allowances; monitor regularly.
- Not financial advice. Read-only tool; we never request keys or sign anything.