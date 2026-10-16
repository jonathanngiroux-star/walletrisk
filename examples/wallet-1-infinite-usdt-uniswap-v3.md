# WalletRisk report — `0xf39b9ffac0fbc5ab3b9c04a729c27053e407e640`

**Scanned:** 2026-10-16T16:38:26Z  
**Grade: F** — 1 unlimited approval(s) actively exposed — revoke now.

- [Ethereum] Revoke USDT allowance to Uniswap V3: SwapRouter… — unlimited, holding $185.

## Ethereum

- Native balance: 0.0359 ETH
- Last activity: 2021-08-23T15:48:58.000000Z
- Holdings checked: 3 tokens
- Findings: **1 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0xf39b9ffac0fbc5ab3b9c04a729c27053e407e640/ethereum

| Sev | Token | Spender | Exposure | Why |
|-----|-------|---------|----------|-----|
| HIGH | USDT | Uniswap V3: SwapRouter | $185 | UNLIMITED approval while holding $185 of USDT. |

## Method & disclaimers

- Only live, on-chain approvals are reported — verified via eth_call at scan time.
- Discovery covers curated majors + your wallet's own transaction history (last ~200 txs + recent transfers).
- Approvals granted via Permit2/off-chain signatures are not visible as allowances; monitor regularly.
- Not financial advice. Read-only tool; we never request keys or sign anything.
