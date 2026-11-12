"""
Base ingestion contracts, untrusted document quoting isolation, and feed path helpers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from asci.core.state import RawSignal

_DELIM_RE = re.compile(r"</?\s*UNTRUSTED_DOCUMENT\s*>", flags=re.IGNORECASE)


def quote_untrusted_text(headline: str, body: str) -> str:
    """
    Isolate untrusted external text inside explicit quoting delimiters.
    Escapes opening/closing tags case-insensitively so adversarial inputs cannot
    break out of or spoof the data container.
    """
    safe_headline = _DELIM_RE.sub("[UNTRUSTED_DELIMITER]", headline)
    safe_body = _DELIM_RE.sub("[UNTRUSTED_DELIMITER]", body)
    return (
        "<UNTRUSTED_DOCUMENT>\n"
        f"HEADLINE: {safe_headline}\n"
        f"BODY: {safe_body}\n"
        "</UNTRUSTED_DOCUMENT>"
    )


def default_feeds_dir() -> Path:
    """Locate the data/feeds directory reliably across working directories."""
    candidates = [
        Path(__file__).resolve().parents[3] / "data" / "feeds",
        Path.cwd() / "data" / "feeds",
        Path.cwd() / "asci-core" / "data" / "feeds",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


class FeedAdapter(Protocol):
    """Protocol implemented by all Stage A external/replay ingestion adapters."""

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Fetch raw signals from external feed or local replay fallback."""
        ...


__all__ = ["FeedAdapter", "RawSignal", "default_feeds_dir", "quote_untrusted_text"]

