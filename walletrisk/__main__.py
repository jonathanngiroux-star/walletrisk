#!/usr/bin/env python3
"""WalletRisk CLI — scan a wallet's approvals across chains, from public data.

Usage:
  python3 -m walletrisk 0xADDRESS            # all chains (free scan)
  python3 -m walletrisk vitalik.eth           # ENS works too
  python3 -m walletrisk 0xADDRESS --chain ethereum --chain base
  python3 -m walletrisk 0xADDRESS --deep     # full-history approvals scan (PRO)
  python3 -m walletrisk 0xADDRESS --json     # machine-readable
  python3 -m walletrisk 0xADDRESS -o report.md
"""

from __future__ import annotations

import argparse
import sys

from .scanner import render_markdown, render_json, scan_wallet
from .chains import CHAINS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walletrisk", description=__doc__)
    p.add_argument("wallet", help="0x address or ENS name")
    p.add_argument("--chain", action="append", choices=list(CHAINS),
                   help="limit scan to chain(s); repeatable")
    p.add_argument("--deep", action="store_true",
                   help="DEEP mode: full-history Approval-event scan (PRO tier)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    p.add_argument("-o", "--out", help="write report to file")
    args = p.parse_args(argv)

    if args.deep:
        from .report import analyze
        from . import format as fmt
        print(f"Deep-scanning {args.wallet} across "
              f"{len(args.chain) if args.chain else len(CHAINS)} chain(s)…",
              file=sys.stderr)
        report = analyze(args.wallet, chains=args.chain)
        out = fmt.markdown(report, deep=True) if not args.json else render_json(report)
    else:
        print(f"Scanning {args.wallet} across "
              f"{len(args.chain) if args.chain else len(CHAINS)} chain(s)…",
              file=sys.stderr)
        report = scan_wallet(args.wallet, chains=args.chain)
        out = render_json(report) if args.json else render_markdown(report)

    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"Report written to {args.out}", file=sys.stderr)
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
