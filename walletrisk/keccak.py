"""Pure-python Keccak-256 (legacy 0x01 padding, NOT SHA3) — zero dependencies.

Used for EIP-55 address checksums and event-signature topic hashes.
Self-tests at import: the ERC-20 Approval topic is a well-known constant
(0x8c5be1e5...) verified against live chain data, so a wrong implementation
fails fast instead of silently corrupting the approvals scanner.
"""

from __future__ import annotations

_MASK = (1 << 64) - 1

_ROUND_CONSTANTS = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]

# rotation offsets r[x][y]
_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]


def _rotl64(v: int, n: int) -> int:
    n &= 63
    if n == 0:
        return v
    return ((v << n) | (v >> (64 - n))) & _MASK


def _keccak_f(lanes: list[int]) -> None:
    for rc in _ROUND_CONSTANTS:
        # theta
        c = [lanes[x] ^ lanes[x + 5] ^ lanes[x + 10] ^ lanes[x + 15] ^ lanes[x + 20]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            dx = d[x]
            for y in range(0, 25, 5):
                lanes[x + y] ^= dx
        # rho + pi:  B[y][(2x+3y) mod 5] = rot(A[x][y], r[x][y])
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl64(lanes[x + 5 * y], _ROT[x][y])
        # chi
        for y in range(0, 25, 5):
            for x in range(5):
                lanes[x + y] = b[x + y] ^ ((~b[(x + 1) % 5 + y] & _MASK) & b[(x + 2) % 5 + y])
        # iota
        lanes[0] ^= rc


_RATE = 136  # bytes (1088-bit rate)


def keccak256(data: bytes) -> bytes:
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _RATE != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80
    lanes = [0] * 25
    for off in range(0, len(padded), _RATE):
        block = padded[off:off + _RATE]
        for i in range(17):
            lanes[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(lanes)
    return b"".join(lanes[i].to_bytes(8, "little") for i in range(4))


def fn_topic(signature: str) -> str:
    """0x-prefixed 32-byte event-signature topic hash."""
    return "0x" + keccak256(signature.encode("ascii")).hex()


# --- self-tests (fail fast on a broken implementation) ---
TOPIC_ERC20_APPROVAL = fn_topic("Approval(address,address,uint256)")
assert TOPIC_ERC20_APPROVAL == "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925", \
    f"keccak self-test failed: {TOPIC_ERC20_APPROVAL}"
TOPIC_ERC721_APPROVAL_FOR_ALL = fn_topic("ApprovalForAll(address,address,bool)")
