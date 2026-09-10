"""One seed for every per-session field.

`hash()` is randomised per process (PYTHONHASHSEED), so a pattern seeded with it
changed on every restart while the session's colour and name (blake2b) survived.
Identity must survive reconnects; it must come from the same stable hash.
"""
from __future__ import annotations

import hashlib

__all__ = ["seed_for"]


def seed_for(session_id: str) -> int:
    return int.from_bytes(hashlib.blake2b(session_id.encode(), digest_size=8).digest(), "big")
