"""Risk model. Deliberately conservative: a fact on chain beats any heuristic.

Severity ladder (per finding):
  HIGH   — live UNLIMITED (>=2^255) approval on a token with balance, or
           an active ApprovalForAll on an NFT collection.
  MEDIUM — live approval > 0 on a valuable token (> $10 exposure), or
           unlimited approval on a zero-balance token (dormant trap).
  LOW    — small live approval, or approval on a zero-balance/scam token.

Wallet grade: F (any HIGH) / C (any MEDIUM) / A (only LOW or nothing)."""

from __future__ import annotations

UNLIMITED = 1 << 255


def _usd(balance_raw: int, decimals: int, rate: float | None) -> float:
    if not rate:
        return 0.0
    return balance_raw / (10 ** decimals) * float(rate)


def enrich_findings(findings: list[dict], native: dict, holdings: list[dict]) -> list[dict]:
    """Attach usd exposure + severity. Mutates and returns sorted findings."""
    bal_by_token = {h["address"]: h for h in holdings}
    for f in findings:
        tok = bal_by_token.get(f["token"])
        if f.get("kind", "").startswith("ERC-721") or f.get("kind", "").startswith("ERC-1155"):
            f["exposure_usd"] = None  # NFT value not modelable from price APIs
            f["severity"] = "HIGH" if f.get("approved_for_all") else "LOW"
            f["why"] = "ApprovalForAll: the operator can move EVERY item in this collection."
            continue
        if tok:
            balance_usd = _usd(tok["raw_balance"], tok["decimals"], tok["exchange_rate"])
            f["token_balance"] = tok["raw_balance"]
            f["token_balance_usd"] = round(balance_usd, 2)
            f["token_symbol"] = tok["symbol"]
            f["token_reputation"] = tok.get("reputation")
            f["decimals"] = tok["decimals"]
        else:
            f["token_balance"] = 0
            f["token_balance_usd"] = 0.0
            f["token_symbol"] = f.get("token_symbol") or "?"
            f["decimals"] = f.get("decimals") or 18
        if f.get("unlimited"):
            f["exposure_usd"] = f["token_balance_usd"]
            if f["token_balance_usd"] and f["token_balance_usd"] > 0:
                f["severity"] = "HIGH"
                f["why"] = (f"UNLIMITED approval while holding "
                            f"${f['token_balance_usd']:,.0f} of {f['token_symbol']}.")
            else:
                f["severity"] = "MEDIUM"
                f["why"] = ("UNLIMITED approval on a token you no longer hold — "
                            "a dormant trap if you ever receive it again.")
        else:
            allowance_usd = _usd(f["allowance_raw"], f["decimals"],
                                 tok["exchange_rate"] if tok else None)
            f["exposure_usd"] = round(min(allowance_usd, f["token_balance_usd"]), 2)
            if f["exposure_usd"] and f["exposure_usd"] >= 10:
                f["severity"] = "MEDIUM"
                f["why"] = f"Live approval worth ~${f['exposure_usd']:,.0f}."
            else:
                f["severity"] = "LOW"
                f["why"] = "Small or zero-value live approval."
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings.sort(key=lambda f: (order.get(f.get("severity"), 3),
                                  -(f.get("exposure_usd") or 0)))
    return findings


def wallet_grade(chain_results: list[dict]) -> tuple[str, str]:
    """chain_results: per-chain dicts with 'findings' (already enriched)."""
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    exposure = 0.0
    for c in chain_results:
        for f in c.get("findings", []):
            counts[f.get("severity", "LOW")] += 1
            if f.get("exposure_usd"):
                exposure += f["exposure_usd"]
    if counts["HIGH"]:
        grade = "F"
        headline = f"{counts['HIGH']} unlimited approval(s) actively exposed — revoke now."
    elif counts["MEDIUM"]:
        grade = "C"
        headline = f"{counts['MEDIUM']} approval(s) worth revoking — real exposure found."
    elif counts["LOW"]:
        grade = "A"
        headline = "Only trivial approvals found — hygiene is good."
    else:
        grade = "A"
        headline = "No live approvals found by this scan."
    return grade, headline


def priority_actions(chain_results: list[dict], limit: int = 8) -> list[str]:
    actions = []
    for c in chain_results:
        for f in c.get("findings", []):
            if f.get("severity") == "HIGH":
                actions.append(
                    f"[{c['chain'].title()}] Revoke {f['token_symbol']} allowance to "
                    f"{f.get('spender_name') or f['spender'][:10]}… — unlimited, "
                    f"holding ${f.get('token_balance_usd') or 0:,.0f}.")
            if len(actions) >= limit:
                return actions
    for c in chain_results:
        for f in c.get("findings", []):
            if f.get("severity") == "MEDIUM":
                actions.append(
                    f"[{c['chain'].title()}] Consider revoking "
                    f"{f['token_symbol']} → {f.get('spender_name') or f['spender'][:10]}…")
            if len(actions) >= limit:
                return actions
    return actions
