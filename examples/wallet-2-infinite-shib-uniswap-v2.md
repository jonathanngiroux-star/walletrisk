# WalletRisk report — `0x297e8e268a79e07d91764d046085a814030a71ad`

**Scanned:** 2026-10-16T16:38:56Z  
**Grade: F** — 1 unlimited approval(s) actively exposed — revoke now.

- [Ethereum] Revoke SHIB allowance to Uniswap V2: Router 02… — unlimited, holding $52.

## Ethereum

- Native balance: 0.0003 ETH
- Last activity: 2021-06-19T22:47:24.000000Z
- Holdings checked: 3 tokens
- Findings: **1 HIGH / 0 MEDIUM / 0 LOW**
- Revoke at: https://revoke.cash/address/0x297e8e268a79e07d91764d046085a814030a71ad/ethereum

| Sev | Token | Spender | Exposure | Why |
|-----|-------|---------|----------|-----|
| HIGH | SHIB | Uniswap V2: Router 02 | $52 | UNLIMITED approval while holding $52 of SHIB. |

## Method & disclaimers

- Only live, on-chain approvals are reported — verified via eth_call at scan time.
- Discovery covers curated majors + your wallet's own transaction history (last ~200 txs + recent transfers).
- Approvals granted via Permit2/off-chain signatures are not visible as allowances; monitor regularly.
- Not financial advice. Read-only tool; we never request keys or sign anything.
