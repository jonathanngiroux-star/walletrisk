"""Walletrisk: free, keyless multi-chain wallet risk reports.
Public data only. Informational — not financial advice.

Exposes: scan_wallet, render_markdown, render_json, classify_input."""

from .scanner import render_markdown, render_json, scan_wallet
from .validate import classify_input

__version__ = "1.0.0"
__all__ = ["scan_wallet", "render_markdown", "render_json", "classify_input"]
