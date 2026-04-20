"""Small shared helpers for ScorpionTrack."""

from __future__ import annotations

import hashlib


def stable_hash(value: str, *, length: int = 12) -> str:
    """Return a short stable hash for non-sensitive identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
