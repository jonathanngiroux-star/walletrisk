"""Strict address validation — lesson learned the hard way: a 41-char address
returns confusing 400/422s from explorers. Validate before anything else."""

from __future__ import annotations

import re

from .keccak import keccak256

_HEX = re.compile(r"^[0-9a-fA-F]+$")


def is_hex_address(s: object) -> bool:
    return (
        isinstance(s, str)
        and s.startswith("0x")
        and len(s) == 42
        and bool(_HEX.match(s[2:]))
    )


def normalize_address(s: str) -> str:
    if not is_hex_address(s):
        raise ValueError(f"not a valid EVM address: {s!r}")
    return s.lower()


def to_checksum(addr: str) -> str:
    """EIP-55 mixed-case checksum encoding."""
    hexpart = normalize_address(addr)[2:]
    digest = keccak256(hexpart.encode("ascii")).hex()
    out = []
    for ch, nibble in zip(hexpart, digest):
        if ch in "0123456789":
            out.append(ch)
        else:
            out.append(ch.upper() if int(nibble, 16) >= 8 else ch)
    return "0x" + "".join(out)


def is_checksum_valid(addr: str) -> bool:
    try:
        return to_checksum(addr) == addr
    except ValueError:
        return False


def is_ens_name(s: object) -> bool:
    return (
        isinstance(s, str)
        and "." in s
        and " " not in s
        and s.lower().endswith(".eth")
        and 5 <= len(s) <= 64
    )


def short(addr: str, n: int = 4) -> str:
    a = addr.lower()
    return f"{a[:2 + n]}…{a[-n:]}"


def classify_input(s: str) -> tuple[str, str]:
    """('address', normalized) | ('ens', name) | raise ValueError."""
    s = s.strip()
    if is_hex_address(s):
        return "address", normalize_address(s)
    if is_ens_name(s):
        return "ens", s
    raise ValueError(
        "input must be a 0x-prefixed 42-char EVM address or an ENS name (.eth)"
    )
