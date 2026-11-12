"""
GDELT & Regional RSS News Ingestion Adapter.
Filters articles for South India automotive corridor relevance before returning RawSignals.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTRSSAdapter:
    """Adapter for GDELT news API and regional trade RSS feeds."""

    CORRIDOR_KEYWORDS = {
        "chennai",
        "kamarajar",
        "ennore",
        "kattupalli",
        "krishnapatnam",
        "tuticorin",
        "cochin",
        "mangalore",
        "oragadam",
        "sriperumbudur",
        "hosur",
        "bidadi",
        "whitefield",
        "irugur",
        "coimbatore",
        "tamil nadu",
        "karnataka",
        "andhra pradesh",
        "nh48",
        "nh44",
    }

    def __init__(
        self,
        fallback_path: str | Path | None = None,
        registry: CanonicalEntityRegistry | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.fallback_path = (
            Path(fallback_path) if fallback_path else default_feeds_dir() / "gdelt_news_sample.json"
        )
        self.registry = registry or get_canonical_registry()
        self.timeout_sec = timeout_sec

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Fetch and relevance-filter articles from GDELT/RSS or local sample archive."""
        payload: dict[str, Any] | None = None
        if not use_fallback:
            try:
                resp = httpx.get(
                    GDELT_DOC_API,
                    params={
                        "query": "(Chennai OR Ennore OR Oragadam OR Krishnapatnam OR Cochin) (port OR strike OR flood OR cyclone)",
                        "mode": "ArtList",
                        "format": "json",
                        "maxrecords": "20",
                    },
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError):
                payload = None

        if payload is None:
            if not self.fallback_path.exists():
                return []
            with open(self.fallback_path, encoding="utf-8") as f:
                payload = json.load(f)

        return self.parse_articles(payload.get("articles", []))

    def is_corridor_relevant(self, text: str) -> bool:
        """Check whether an article mentions a registered corridor entity or regional keyword."""
        lowered = text.lower()
        if any(kw in lowered for kw in self.CORRIDOR_KEYWORDS):
            return True
        matches = self.registry.resolve_entities(text, min_score=0.82)
        return len(matches) > 0

    def parse_articles(self, articles: list[dict[str, Any]]) -> list[RawSignal]:
        """Convert relevant articles into untrusted RawSignal containers."""
        signals: list[RawSignal] = []
        for idx, art in enumerate(articles):
            headline = str(art.get("headline") or art.get("title") or "").strip()
            body = str(art.get("body") or art.get("snippet") or headline).strip()
            combined = f"{headline} {body}"

            if not self.is_corridor_relevant(combined):
                continue

            tier_str = str(art.get("trust_tier", "TIER_B")).upper()
            trust_tier = (
                TrustTier(tier_str) if tier_str in TrustTier._value2member_map_ else TrustTier.TIER_B
            )

            pub_raw = art.get("published_at") or art.get("seendate")
            published_at = _parse_ts(pub_raw) or datetime.now(UTC)
            art_id = str(art.get("article_id") or f"GDELT_{idx}")
            source_name = str(art.get("source") or art.get("domain") or "GDELT_RSS")

            signals.append(
                RawSignal(
                    signal_id=f"SIG_{art_id}",
                    source_feed=f"GDELT:{source_name}",
                    trust_tier=trust_tier,
                    raw_headline=headline,
                    raw_text=body,
                    published_at=published_at,
                    source_url=art.get("url"),
                    metadata={"article_id": art_id, "source": source_name},
                )
            )
        return signals


def _parse_ts(val: str | None) -> datetime | None:
    if not isinstance(val, str) or not val.strip():
        return None
    cleaned = val.strip()
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(cleaned)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None

