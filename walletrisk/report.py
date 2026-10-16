"""Report orchestrator: address -> full multi-chain risk report (data dict)."""

from __future__ import annotations

import datetime as dt
import concurrent.futures as cf

from .balances import fetch_chain_snapshot, fetch_recent_activity
from .chains import CHAINS
from .scoring import (approval_score, composite, concentration_score,
                      dormancy_score, grade, verdict)
from .validate import classify_input, normalize_address, short, to_checksum
from . import approvals as ap
from . import client
from .approvals import approvals_supported


def _days_since(ts_iso: str | None) -> float | None:
    if not ts_iso:
        return None
    when = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - when).total_seconds() / 86400


def analyze(input_str: str, chains: list[str] | None = None,
            with_approvals: bool = True, top_tokens: int = 40) -> dict:
    """Full report. `input_str` = 0x address or ENS name."""
    kind, value = classify_input(input_str)
    if kind == "ens":
        address = normalize_address(client.resolve_ens(value))
        resolved_from = value
    else:
        address = value
        resolved_from = None

    chains = chains or list(CHAINS.keys())
    chains = [c for c in chains if c in CHAINS]

    # 1) balances across chains (parallel, threads)
    snapshots: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_chain_snapshot, c, address, top_tokens): c
                for c in chains}
        for fut in cf.as_completed(futs):
            c = futs[fut]
            try:
                snapshots[c] = fut.result()
            except Exception as e:
                errors[c] = f"{type(e).__name__}: {e}"

    active = {c: s for c, s in snapshots.items() if s["total_usd"] > 0 or True}
    total_usd = sum(s["total_usd"] for s in snapshots.values())

    # 2) approvals on chains with token activity
    live_approvals: list[dict] = []
    approval_events_count = 0
    approval_skipped = 0
    unsupported_chains: list[str] = []
    if with_approvals:
        approval_chains = [c for c, s in snapshots.items()
                            if s["native"]["usd"] > 0 or s["tokens"]]
        for c in approval_chains:
            if not approvals_supported(c):
                if c == "zksync":
                    unsupported_chains.append(c)
                continue
            try:
                events = ap.fetch_approval_events(c, address)
                approval_events_count += len(events)
                parsed = ap.parse_approval_events(events)
                if parsed:
                    live, skipped = ap.check_live(c, address, parsed,
                                                  snapshots[c]["token_meta"])
                    approval_skipped += skipped
                    for a in live:
                        a["chain"] = c
                    live_approvals.extend(live)
            except Exception as e:
                errors[f"{c}:approvals"] = f"{type(e).__name__}: {e}"

    # 3) activity / dormancy — try each scanned chain until one has activity
    activity = None
    for c in chains:
        if c not in snapshots:
            continue
        act = fetch_recent_activity(c, address)
        if act["last_tx"]:
            activity = act
            break
    if activity is None:
        # no from-side txs anywhere: fall back to the counters of the chain
        # with the highest balance so tx_count is still populated
        fallback = max(snapshots, key=lambda c: snapshots[c]["total_usd"]) \
            if snapshots else None
        activity = fetch_recent_activity(fallback, address) if fallback else {}
        activity["no_activity_found"] = True

    # 4) scores
    assets = []
    for s in snapshots.values():
        assets.append({"label": f"{s['native']['symbol']} ({s['chain']})",
                       "usd": s["native"]["usd"], "kind": "native"})
        assets.extend({"label": f"{t['symbol']} ({s['chain']})",
                       "usd": t["usd"], "kind": "token"}
                      for t in s["tokens"] if t["usd"] > 0)
    conc_score, weighted = concentration_score(total_usd, assets)
    appr_score, unlimited_approvals = approval_score(live_approvals)
    days_idle = _days_since(activity.get("last_tx")) if activity else None
    tx_count = activity.get("tx_count", 0) if activity else 0
    dorm_score, dorm_note = dormancy_score(days_idle, tx_count)
    overall = composite({"approvals": appr_score, "concentration": conc_score,
                         "dormancy": dorm_score})
    grade_letter = grade(overall)
    # hard floor: an actively-exposed UNLIMITED approval is never "low risk"
    exposed_unlimited = [a for a in live_approvals
                        if a.get("unlimited") and a.get("usd_value_at_risk")]
    floor_note = None
    if exposed_unlimited and grade_letter in ("A", "B"):
        grade_letter = "C"
        floor_note = (f"{len(exposed_unlimited)} actively-exposed unlimited "
                      f"approval(s) force a minimum grade of C")

    return {
        "input": input_str,
        "address": address,
        "address_short": short(address),
        "checksum": to_checksum(address),
        "resolved_from": resolved_from,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_usd": total_usd,
        "chains_scanned": chains,
        "chain_errors": errors,
        "per_chain": {c: {
            "native": s["native"], "tokens": s["tokens"],
            "total_usd": s["total_usd"], "ens": s["ens"],
            "is_contract": s["is_contract"], "proxy_type": s["proxy_type"],
        } for c, s in snapshots.items()},
        "approvals": {
            "live": live_approvals,
            "unlimited": unlimited_approvals,
            "events_scanned": approval_events_count,
            "skipped_pairs": approval_skipped,
            "unsupported_chains": unsupported_chains,
        },
        "activity": {"last_tx": activity.get("last_tx") if activity else None,
                      "days_idle": days_idle, "tx_count": tx_count},
        "scores": {"approvals": appr_score, "concentration": conc_score,
                   "dormancy": dorm_score, "overall": overall},
        "grade": grade_letter,
        "grade_floor_note": floor_note,
        "verdict": verdict(grade_letter),
    }
