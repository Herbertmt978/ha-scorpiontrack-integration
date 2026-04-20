"""Small shared helpers for ScorpionTrack."""

from __future__ import annotations

import hashlib


def stable_hash(value: str, *, length: int = 12) -> str:
    """Return a short stable hash for non-sensitive identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def mask_email(value: str) -> str:
    """Return a lightly redacted email address for logging."""
    cleaned = value.strip()
    if not cleaned:
        return "<empty>"
    if "@" not in cleaned:
        return "***"

    local, _, domain = cleaned.partition("@")
    masked_local = f"{local[:1]}***" if local else "***"
    return f"{masked_local}@{domain}"


def mask_token(value: str, *, visible: int = 4) -> str:
    """Return a lightly redacted token for logging."""
    cleaned = value.strip()
    if not cleaned:
        return "<empty>"
    if len(cleaned) <= visible * 2:
        return "*" * len(cleaned)
    return f"{cleaned[:visible]}...{cleaned[-visible:]}"
