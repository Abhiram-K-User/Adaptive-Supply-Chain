"""
GDELT & Regional RSS News Ingestion Adapter.
Filters articles for South India automotive corridor relevance before returning RawSignals.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import RawSignal, TrustTier
from asci.ingestion.base import default_feeds_dir

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
_HTML_TAG_RE = re.compile(r"<[^>]+>")


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

    DISRUPTION_KEYWORDS = {
        "cyclone",
        "storm",
        "surge",
        "flood",
        "waterlog",
        "inundat",
        "heavy rain",
        "downpour",
        "landslide",
        "strike",
        "boycott",
        "protest",
        "slowdown",
        "congest",
        "backlog",
        "delay",
        "blockade",
        "closure",
        "closed",
        "halt",
        "suspend",
        "disrupt",
        "outage",
        "derail",
        "shutdown",
        "stranded",
        "bottleneck",
        "red alert",
        "orange alert",
        "low-pressure",
        "low pressure",
        "depression",
        "tariff",
        "embargo",
        "warning",
    }

    def __init__(
        self,
        fallback_path: str | Path | None = None,
        registry: CanonicalEntityRegistry | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.fallback_path = (
            Path(fallback_path) if fallback_path else default_feeds_dir() / "gdelt_news_sample.json"
        )
        self.registry = registry or get_canonical_registry()
        env_timeout = os.environ.get("ASCI_FEED_TIMEOUT_SECONDS")
        self.timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else (float(env_timeout) if env_timeout else 6.0)
        )
        self.gdelt_url = os.environ.get("ASCI_GDELT_API_URL") or GDELT_DOC_API
        self.rss_url = os.environ.get("ASCI_NEWS_RSS_URL") or GOOGLE_NEWS_RSS_URL
        self.last_fetch_mode: str = "uninitialized"
        self.last_error: str | None = None
        self.last_fetched_at: str | None = None

    def fetch(self, use_fallback: bool = True) -> list[RawSignal]:
        """Fetch and relevance-filter articles from GDELT, live India News RSS, or local archive."""
        payload: dict[str, Any] | None = None
        self.last_error = None
        headers = {"User-Agent": "ASCI-Control-Tower/2.0"}

        if not use_fallback:
            # 1. Try GDELT Doc v2 API first
            try:
                resp = httpx.get(
                    self.gdelt_url,
                    params={
                        "query": "(Chennai OR Ennore OR Oragadam OR Krishnapatnam OR Cochin) (port OR strike OR flood OR cyclone)",
                        "mode": "ArtList",
                        "format": "json",
                        "maxrecords": "20",
                    },
                    headers=headers,
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                payload = resp.json()
                self.last_fetch_mode = "live_gdelt"
            except (httpx.HTTPError, ValueError) as exc:
                self.last_error = f"GDELT {type(exc).__name__}: {exc}"
                payload = None

            # 2. Live Google News India RSS backup if GDELT times out / unavailable
            if payload is None:
                try:
                    rss_resp = httpx.get(
                        self.rss_url,
                        params={
                            "q": "(Chennai OR Ennore OR Krishnapatnam OR Tuticorin OR Cochin OR NH48) (port OR cyclone OR flood OR strike OR cargo)",
                            "hl": "en-IN",
                            "gl": "IN",
                            "ceid": "IN:en",
                        },
                        headers=headers,
                        timeout=self.timeout_sec,
                    )
                    rss_resp.raise_for_status()
                    rss_articles = self._parse_rss_xml(rss_resp.text)
                    payload = {"articles": rss_articles}
                    self.last_fetch_mode = "live_rss"
                    self.last_error = None
                except (httpx.HTTPError, ET.ParseError, ValueError) as rss_exc:
                    self.last_error = (
                        f"{self.last_error}; RSS {type(rss_exc).__name__}: {rss_exc}"
                        if self.last_error
                        else f"RSS {type(rss_exc).__name__}: {rss_exc}"
                    )
                    payload = None

        if payload is None:
            self.last_fetch_mode = "fallback"
            if not self.fallback_path.exists():
                return []
            with open(self.fallback_path, encoding="utf-8") as f:
                payload = json.load(f)

        self.last_fetched_at = datetime.now(UTC).isoformat()
        return self.parse_articles(payload.get("articles", []))

    @staticmethod
    def _parse_rss_xml(xml_text: str) -> list[dict[str, Any]]:
        """Parse Google News / generic RSS 2.0 XML into article dicts."""
        root = ET.fromstring(xml_text)
        articles: list[dict[str, Any]] = []
        for item in root.findall(".//item")[:20]:
            title = html.unescape((item.findtext("title") or "").strip())
            desc_raw = html.unescape((item.findtext("description") or "").strip())
            desc_clean = _HTML_TAG_RE.sub(" ", desc_raw).strip()
            source_el = item.find("source")
            source_name = (
                source_el.text.strip()
                if source_el is not None and source_el.text
                else "GOOGLE_NEWS_RSS"
            )
            digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10].upper()
            articles.append(
                {
                    "article_id": f"RSS_{digest}",
                    "headline": title,
                    "body": desc_clean or title,
                    "source": source_name,
                    "trust_tier": "TIER_B",
                    "published_at": (item.findtext("pubDate") or "").strip(),
                    "url": (item.findtext("link") or "").strip() or None,
                }
            )
        return articles

    def is_corridor_relevant(self, text: str) -> bool:
        """Check whether an article mentions a registered corridor entity AND a disruption signal."""
        lowered = text.lower()
        has_disruption = any(dk in lowered for dk in self.DISRUPTION_KEYWORDS)
        if not has_disruption:
            return False
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

