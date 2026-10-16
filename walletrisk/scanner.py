"""Scanner orchestrator: one wallet, N chains, one report.

Flow per chain:
  1. discovery     — holdings + native balance + interaction candidates
                     (Blockscout v2 REST, keyless)
  2. spender set   = curated registry (majors always checked)
                   ∪ wallet's own interaction history (long tail)
  set minus EOA/unknown without code. Filter code via eth_getCode? too many
  calls; Blockscout tells us is_contract for the finals only.
  3. live checks   — eth_call allowance()/isApprovedForAll (publicnode, keyless)
  4. enrichment    — metadata names + severity + exposure (Blockscout)
  5. render        — console/markdown/JSON

A failed chain is reported as 'error', never silently skipped."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .chains import CHAINS, DEFAULT_CHAINS
from .checks import batch_allowances, batch_nft_approvals
from .discover import fetch_holdings, fetch_interactions, fetch_native, resolve_ens
from .registry import nft_hubs_for, spenders_for
from .risk import enrich_findings, priority_actions, wallet_grade
from .validate import classify_input


def scan_chain(chain: str, address: str, deep: bool = False) -> dict:
    meta = CHAINS[chain]
    host, rpc = meta["host"], meta["rpc"]
    t0 = time.time()
    result = {"chain": chain, "label": meta["label"], "address": address,
              "revoke_url": f"https://revoke.cash/address/{address}/{meta['revoke_slug']}",
              "explorer_url": f"{meta['explorer']}/address/{address}"}

    try:
        holdings = fetch_holdings(host, address)
    except Exception as e:
        result["error"] = f"holdings discovery failed: {e}"
        return result
    try:
        native = fetch_native(host, address)
    except Exception as e:
        native = {"raw_balance": 0, "exchange_rate": None, "last_active": None}
        result["native_error"] = str(e)
    try:
        interactors, meta_tx = fetch_interactions(host, address)
    except Exception as error:
        interactors, meta_tx = [], {"last_active": None, "first_active": None}
        result["interaction_error"] = str(error)

    result["holdings"] = holdings
    result["native"] = native
    result["last_active"] = meta_tx.get("last_active")

    # --- spender candidate set ---------------------------------------------
    registry = spenders_for(chain)
    spender_set: dict[str, str | None] = {s["address"]: s["registry_name"] for s in registry}
    for cand in interactors:
        spender_set.setdefault(cand, None)  # unnamed, from wallet history

    # --- live allowance checks ---------------------------------------------
    pairs = []
    for tok in holdings:
        if not tok["kind"].startswith("ERC-20"):
            continue
        for saddr, sname in spender_set.items():
            pairs.append({
                "token": tok["address"], "spender": saddr,
                "token_symbol": tok["symbol"], "spender_name": sname,
                "decimals": tok["decimals"], "kind": "ERC-20",
            })
    live = batch_allowances(rpc, address, pairs)
    # drop zero allowances
    live = [f for f in live if f["allowance_raw"] > 0]
    # name enrichment for unnamed spenders
    _name_spenders(result, live)

    # --- NFT approvals-for-all ----------------------------------------------
    nft_holdings = [h for h in holdings if h["kind"].startswith("ERC-721")
                    or h["kind"].startswith("ERC-1155")]
    nft_ops = nft_hubs_for(chain)
    nft_findings = batch_nft_approvals(rpc, address, nft_holdings, nft_ops)
    nft_rows = []
    for nf in nft_findings:
        nft = nf["nft"]
        nft_rows.append({
            "token": nft["address"], "spender": nf["operator"]["address"],
            "token_symbol": nft["symbol"], "spender_name": nf["operator"]["registry_name"],
            "approved_for_all": True, "kind": nft["kind"], "allowance_raw": None,
            "unlimited": True, "is_nft": True,
        })
    _name_spenders(result, nft_rows)

    all_findings = live + nft_rows
    enrich_findings(all_findings, native, holdings)
    result["findings"] = all_findings
    result["counts"] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in all_findings:
        result["counts"][f.get("severity", "LOW")] += 1
    result["duration_s"] = round(time.time() - t0, 1)
    return result


def _name_spenders(result: dict, rows: list[dict]) -> None:
    """Fill spender_name via Blockscout /addresses/{h} for unnamed spenders."""
    from .client import blockscout
    host = CHAINS[result["chain"]]["host"]
    for row in rows:
        if row.get("spender_name"):
            continue
        try:
            d = blockscout(host, f"/addresses/{row['spender']}")
            row["spender_name"] = d.get("name") or (
                "contract" if d.get("is_contract") else "EOA (externally owned addr)")
        except Exception:
            row["spender_name"] = "unknown contract"


def scan_wallet(input_addr: str, chains: list[str] | None = None, deep: bool = False) -> dict:
    """Full multi-chain scan. Resolves ENS. Returns the report dict."""
    kind, value = classify_input(input_addr)
    if kind == "ens":
        address = resolve_ens(value)
        ens_name = value
    else:
        address, ens_name = value, None

    use_chains = [c for c in (chains or DEFAULT_CHAINS) if c in CHAINS]
    if not use_chains:
        raise ValueError("no valid chains requested")
    chain_results: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(scan_chain, c, address): c for c in use_chains}
        for fut in as_completed(futures):
            chain_results.append(fut.result())
    order = {c: i for i, c in enumerate(use_chains)}
    chain_results.sort(key=lambda r: order[r["chain"]])

    grade, headline = wallet_grade(chain_results)
    actions = priority_actions(chain_results)
    return {
        "address": address,
        "input": input_addr,
        "ens": ens_name,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grade": grade,
        "headline": headline,
        "actions": actions,
        "chains": chain_results,
        "tool": "WalletRisk v1",
        "notes": [
            "Only live, on-chain approvals are reported — verified via eth_call at scan time.",
            "Discovery covers curated majors + your wallet's own transaction history (last ~200 txs + recent transfers).",
            "Approvals granted via Permit2/off-chain signatures are not visible as allowances; monitor regularly.",
            "Not financial advice. Read-only tool; we never request keys or sign anything.",
        ],
    }


def use_chchains_list(use_chains: list[str]) -> list[str]:
    # defensive: a scan with zero valid chains should raise, not hang
    if not use_chains:
        raise ValueError("no valid chains requested")
    return use_chains


# --- renderers ---------------------------------------------------------------

def render_markdown(report: dict) -> str:
    addr = report["address"]
    ens = f" ({report['ens']})" if report.get("ens") else ""
    lines = [
        f"# WalletRisk report — `{addr}`{ens}",
        "",
        f"**Scanned:** {report['scanned_at']}  ",
        f"**Grade: {report['grade']}** — {report['headline']}",
        "",
    ]
    for act in report["actions"]:
        lines.append(f"- {act}")
    if not report["actions"]:
        lines.append("- No revokes needed according to this scan. 🎉")
    lines.append("")
    for c in report["chains"]:
        lines.append(f"## {c['label']}")
        lines.append("")
        if c.get("error"):
            lines.append(f"⚠️ Chain skipped: {c['error']}")
            lines.append("")
            continue
        lines.append(f"- Native balance: {c['native']['raw_balance'] / 1e18:.4f} {CHAINS[c['chain']]['native']}")
        last = c.get("last_active")
        if last:
            lines.append(f"- Last activity: {last}")
        lines.append(f"- Holdings checked: {len(c.get('holdings', []))} tokens")
        lines.append(f"- Findings: **{c['counts']['HIGH']} HIGH / {c['counts']['MEDIUM']} MEDIUM / {c['counts']['LOW']} LOW**")
        lines.append(f"- Revoke at: {c['revoke_url']}")
        lines.append("")
        if c.get("findings"):
            lines.append("| Sev | Token | Spender | Exposure | Why |")
            lines.append("|-----|-------|---------|----------|-----|")
            for f in c["findings"]:
                exp = f"${f.get('exposure_usd') or 0:,.0f}" if f.get("exposure_usd") is not None else "—"
                lines.append(f"| {f['severity']} | {f.get('token_symbol','?')} | "
                             f"{f.get('spender_name','?')} | {exp} | {f.get('why','')} |")
            lines.append("")
    lines.append("## Method & disclaimers")
    lines.append("")
    for n in report["notes"]:
        lines.append(f"- {n}")
    return "\n".join(lines)


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, default=str)
