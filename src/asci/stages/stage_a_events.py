"""
Stage A: Live Event Intelligence & Entity Resolution.
Converts heterogeneous signals into structured disruption records grounded in canonical registry IDs.
Implements tool-isolated extraction over untrusted quoting containers per Section 9 of the PRD.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityMatch, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    RawSignal,
    TrustTier,
)
from asci.ingestion.base import quote_untrusted_text


class ExtractedEventFields(BaseModel):
    """Strict Pydantic schema produced by the zero-tool Stage A extractor."""

    model_config = ConfigDict(frozen=True)

    event_type: DisruptionEventType
    severity: float = Field(ge=0.0, le=1.0)
    estimated_duration_days: float = Field(gt=0.0, le=30.0)
    mentioned_spans: list[str] = Field(default_factory=list)


class ExtractorBackend(Protocol):
    """Zero-tool extractor protocol operating exclusively over quoted untrusted text."""

    def extract(self, quoted_document: str, signal: RawSignal) -> ExtractedEventFields:
        """Parse quoted text into typed disruption fields without tool access."""
        ...


class DeterministicExtractor:
    """
    Deterministic zero-tool NLP/rule classifier covering all 7 regional event categories.
    Filters imperative prompt-injection directives, separates HEADLINE vs BODY weighting,
    scores all categories cleanly using word-boundary regexes, and bounds numeric outputs.
    """

    _CATEGORY_KEYWORDS: dict[DisruptionEventType, tuple[str, ...]] = {
        DisruptionEventType.HAZARD_PORT: (
            "cyclone",
            "cyclonic",
            "storm surge",
            "typhoon",
            "gale",
            "harbour",
            "harbor",
            "berth closure",
            "port closure",
            "crane operations",
            "vessel calls dropped",
            "heavy swell",
        ),
        DisruptionEventType.HAZARD_ROAD: (
            "highway",
            "waterlogging",
            "flood",
            "flooding",
            "inundated",
            "bridge",
            "landslide",
            "nh48",
            "nh44",
            "nh544",
            "stranded",
            "road closure",
        ),
        DisruptionEventType.PORT_CONGESTION_STRIKE: (
            "strike",
            "stevedore",
            "union",
            "walkout",
            "berth backlog",
            "customs outage",
            "slowdown",
            "slows",
            "congestion",
        ),
        DisruptionEventType.RAIL_DISRUPTION: (
            "rail disruption",
            "railway disruption",
            "rail blockage",
            "track flooding",
            "track blocked",
            "derailment",
            "signal failure",
            "block train suspended",
            "rail cut",
            "railway suspended",
        ),
        DisruptionEventType.SHIPPING_SCHEDULE: (
            "blank sailing",
            "vessel omission",
            "carrier diversion",
            "schedule shift",
        ),
        DisruptionEventType.TRADE_POLICY: (
            "tariff",
            "customs rule",
            "import duty",
            "export ban",
            "policy shift",
        ),
        DisruptionEventType.PLANT_OUTAGE: (
            "plant outage",
            "assembly stoppage",
            "factory fire",
            "line shutdown",
            "supplier breakdown",
        ),
    }

    _CATEGORY_PRIORITY: list[DisruptionEventType] = [
        DisruptionEventType.HAZARD_PORT,
        DisruptionEventType.PORT_CONGESTION_STRIKE,
        DisruptionEventType.RAIL_DISRUPTION,
        DisruptionEventType.PLANT_OUTAGE,
        DisruptionEventType.SHIPPING_SCHEDULE,
        DisruptionEventType.TRADE_POLICY,
        DisruptionEventType.HAZARD_ROAD,
    ]

    _HIGH_SEV_TERMS = (
        "red alert",
        "red warning",
        "severe",
        "suspended",
        "halted",
        "closed",
        "closure",
        "shutdown",
    )
    _MED_SEV_TERMS = (
        "orange",
        "strike",
        "slowdown",
        "slows",
        "waterlogging",
        "backlog",
        "delayed",
        "congestion",
        "disrupts",
        "stranded",
    )

    _INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass|discard|reset|cancel|drop)\b"
            r".{0,45}\b(previous|prior|earlier|above|system|rules?|instructions?|guidelines?|prompt|verifier|policy|constraints?|classification)\b",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^\s*(system\s+override|developer\s+note|admin\s+command|new\s+instructions?|"
            r"prompt\s+override|tool\s*call|execute\s+tool|assistant\s*:)\b",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"\bset\s+[a-z_]+\s*=|\bbypass\s+verifier\b|\bexecute\s+tool\b",
            flags=re.IGNORECASE,
        ),
    )

    @classmethod
    def _is_injection_clause(cls, segment: str) -> bool:
        return any(pat.search(segment) for pat in cls._INJECTION_PATTERNS)

    @classmethod
    def _clean_segment(cls, text: str) -> str:
        """Drop lines or clauses containing adversarial instruction-override syntax."""
        kept: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            if cls._is_injection_clause(line):
                continue
            # Also inspect semicolon-separated subclauses
            subclauses = [c.strip() for c in line.split(";") if not cls._is_injection_clause(c)]
            if subclauses:
                kept.append("; ".join(subclauses))
        return "\n".join(kept)

    @classmethod
    def _unwrap_sections(cls, quoted_document: str) -> tuple[str, str]:
        """Extract HEADLINE and BODY sections bounded by <UNTRUSTED_DOCUMENT> tags."""
        m = re.search(
            r"<UNTRUSTED_DOCUMENT>\s*(.*?)\s*</UNTRUSTED_DOCUMENT>",
            quoted_document,
            flags=re.DOTALL,
        )
        content = m.group(1) if m else quoted_document

        head_match = re.search(
            r"\AHEADLINE:\s*(.*?)(?:\nBODY:\s*(.*))?\Z",
            content,
            flags=re.DOTALL,
        )
        if head_match:
            raw_head = head_match.group(1) or ""
            raw_body = head_match.group(2) or ""
        else:
            raw_head = ""
            raw_body = content

        clean_head = cls._clean_segment(raw_head)
        clean_body = cls._clean_segment(raw_body)
        return clean_head, clean_body

    @classmethod
    def _unwrap_quoted_body(cls, quoted_document: str) -> str:
        """Extract sanitized text bounded by <UNTRUSTED_DOCUMENT> tags."""
        head, body = cls._unwrap_sections(quoted_document)
        return f"{head}\n{body}".strip()

    @staticmethod
    def _count_term_matches(text_low: str, term: str) -> int:
        pat = rf"(?<!\w){re.escape(term)}(?!\w)"
        return len(re.findall(pat, text_low))

    def extract(self, quoted_document: str, signal: RawSignal) -> ExtractedEventFields:
        """Classify disruption category, severity, and duration deterministically."""
        clean_head, clean_body = self._unwrap_sections(quoted_document)
        head_low = clean_head.lower()
        body_low = clean_body.lower()
        combined_low = f"{head_low}\n{body_low}".strip()

        matched_spans: list[str] = []

        # 1. Event type classification via HEADLINE-weighted (3.0x) vs BODY (1.0x) scoring
        event_type = signal.hint_event_type
        if event_type is None:
            scores: dict[DisruptionEventType, float] = {}
            for cat in self._CATEGORY_PRIORITY:
                score = 0.0
                for kw in self._CATEGORY_KEYWORDS[cat]:
                    h_hits = self._count_term_matches(head_low, kw)
                    b_hits = self._count_term_matches(body_low, kw)
                    if h_hits or b_hits:
                        matched_spans.append(kw)
                    score += (h_hits * 3.0) + (min(b_hits, 2) * 1.0)
                scores[cat] = score

            best_cat = DisruptionEventType.HAZARD_ROAD
            best_score = 0.0
            for cat in self._CATEGORY_PRIORITY:
                if scores[cat] > best_score:
                    best_score = scores[cat]
                    best_cat = cat
            event_type = best_cat
        else:
            # Record any matching spans for traceability
            for cat in self._CATEGORY_PRIORITY:
                for kw in self._CATEGORY_KEYWORDS[cat]:
                    if self._count_term_matches(combined_low, kw) > 0:
                        matched_spans.append(kw)

        # 2. Severity estimation
        if signal.hint_severity is not None:
            severity = float(signal.hint_severity)
        elif any(self._count_term_matches(combined_low, term) > 0 for term in self._HIGH_SEV_TERMS):
            severity = 0.85
        elif any(self._count_term_matches(combined_low, term) > 0 for term in self._MED_SEV_TERMS):
            severity = 0.62
        else:
            severity = 0.45
        severity = max(0.05, min(1.0, round(severity, 2)))

        # 3. Duration estimation
        if signal.hint_duration_days is not None:
            duration = float(signal.hint_duration_days)
        else:
            hour_match = re.search(r"(\d+(?:\.\d+)?)\s*[- ]*hours?", combined_low)
            day_match = re.search(r"(\d+(?:\.\d+)?)\s*[- ]*days?", combined_low)
            if day_match:
                duration = float(day_match.group(1))
            elif hour_match:
                duration = max(0.5, round(float(hour_match.group(1)) / 24.0, 2))
            elif severity >= 0.8:
                duration = 4.0
            elif severity >= 0.6:
                duration = 2.0
            else:
                duration = 1.0
        duration = max(0.5, min(30.0, round(duration, 2)))

        return ExtractedEventFields(
            event_type=event_type,
            severity=severity,
            estimated_duration_days=duration,
            mentioned_spans=list(dict.fromkeys(matched_spans)),
        )


class StageAEventPerception:
    """
    Stage A Operator: Disruption Signal Ingestion, Classification & Canonical Entity Resolution.
    """

    _TRUST_CONFIDENCE = {
        TrustTier.TIER_A: 0.92,
        TrustTier.TIER_B: 0.78,
        TrustTier.TIER_C: 0.55,
    }

    def __init__(
        self,
        registry: CanonicalEntityRegistry | None = None,
        extractor: ExtractorBackend | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.extractor = extractor or DeterministicExtractor()

    def parse_raw_signal(self, signal: RawSignal) -> DisruptionEvent:
        """
        Parse an untrusted RawSignal into a canonical DisruptionEvent using
        the tool-isolated extractor and multi-entity/geospatial gazetteer.
        """
        quoted = quote_untrusted_text(signal.raw_headline, signal.raw_text)
        extracted = self.extractor.extract(quoted, signal)

        # Strip injection lines before running gazetteer matching
        safe_text = DeterministicExtractor._unwrap_quoted_body(quoted)

        # Multi-source entity resolution: hint -> text gazetteer -> polygon -> point radius
        matches: list[EntityMatch] = []
        if signal.hint_entity_id and self.registry.validate_id(signal.hint_entity_id):
            ent = self.registry.get(signal.hint_entity_id)
            matches.append(
                EntityMatch(
                    entity=ent,
                    score=1.0,
                    method="EXACT",
                    matched_span=signal.hint_entity_id,
                )
            )

        text_matches = self.registry.resolve_entities(safe_text, min_score=0.78)
        matches.extend(text_matches)

        if signal.polygon:
            poly_matches = self.registry.resolve_by_polygon(signal.polygon, buffer_km=15.0)
            matches.extend(poly_matches)
        elif signal.latitude is not None and signal.longitude is not None:
            coord_matches = self.registry.resolve_by_coordinates(
                signal.latitude, signal.longitude, radius_km=45.0
            )
            if (
                not coord_matches
                and signal.source_feed == "GDACS"
                and extracted.event_type == DisruptionEventType.HAZARD_PORT
            ):
                offshore_matches = self.registry.resolve_by_coordinates(
                    signal.latitude, signal.longitude, radius_km=220.0
                )
                coord_matches = [
                    m for m in offshore_matches if m.entity.entity_type.value == "PORT"
                ]
            matches.extend(coord_matches)

        # Deduplicate while preserving highest-ranked primary entity
        seen_ids: list[str] = []
        for m in matches:
            if m.entity.id not in seen_ids:
                seen_ids.append(m.entity.id)

        if not seen_ids:
            raise ValueError(
                f"Stage A grounding failure: signal '{signal.signal_id}' resolved no canonical corridor entities."
            )

        primary_id = seen_ids[0]
        affected_ids = seen_ids

        # Deterministic event ID derived from signal_id
        digest = hashlib.sha1(signal.signal_id.encode("utf-8")).hexdigest()[:8].upper()
        event_id = f"EVT_{digest}"

        base_conf = self._TRUST_CONFIDENCE.get(signal.trust_tier, 0.75)
        source_urls = [signal.source_url] if signal.source_url else []

        return DisruptionEvent(
            event_id=event_id,
            event_type=extracted.event_type,
            status=EventStatus.NEW,
            primary_entity_id=primary_id,
            affected_entity_ids=affected_ids,
            severity=extracted.severity,
            estimated_duration_days=extracted.estimated_duration_days,
            source_feed=signal.source_feed,
            raw_headline=signal.raw_headline,
            raw_text=signal.raw_text,
            timestamp=signal.published_at,
            corroboration_count=1,
            confidence=base_conf,
            spatial_footprint=signal.polygon,
            source_urls=source_urls,
        )

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage A perception.
        Enforces canonical entity grounding and immutable state transition.
        """
        _ = rng
        t0 = time.perf_counter()

        # Case 1: Pre-grounded event already present in state
        if state.event:
            event = state.event
            if not self.registry.validate_id(event.primary_entity_id):
                error_msg = (
                    f"Stage A validation error: entity '{event.primary_entity_id}' "
                    "is not in Canonical Registry."
                )
                return state, OperatorResult(
                    operator_type=OperatorType.STAGE_A_PERCEPTION,
                    success=False,
                    message=error_msg,
                    error=error_msg,
                )
            for eid in event.affected_entity_ids:
                if not self.registry.validate_id(eid):
                    error_msg = (
                        f"Stage A validation error: affected entity '{eid}' "
                        "is not in Canonical Registry."
                    )
                    return state, OperatorResult(
                        operator_type=OperatorType.STAGE_A_PERCEPTION,
                        success=False,
                        message=error_msg,
                        error=error_msg,
                    )

        # Case 2: Untrusted RawSignal provided -> tool-isolated extraction & gazetteer resolution
        elif state.raw_signal is not None:
            try:
                event = self.parse_raw_signal(state.raw_signal)
            except ValueError as exc:
                error_msg = str(exc)
                return state, OperatorResult(
                    operator_type=OperatorType.STAGE_A_PERCEPTION,
                    success=False,
                    message=error_msg,
                    error=error_msg,
                )

        # Case 3: Walking skeleton seed fallback when neither event nor raw_signal provided
        else:
            primary_entity = self.registry.get("PORT_KAMARAJAR")
            event = DisruptionEvent(
                event_id="EVT_SEED_MICHAUNG_001",
                event_type=DisruptionEventType.HAZARD_PORT,
                status=EventStatus.NEW,
                primary_entity_id=primary_entity.id,
                affected_entity_ids=["PORT_KAMARAJAR", "CFS_ENNORE_LOGISTICS", "PORT_CHENNAI"],
                severity=0.85,
                estimated_duration_days=4.0,
                source_feed="IMD_GDACS_PORTWATCH",
                raw_headline="Severe Cyclonic Storm warning issued for North Tamil Nadu coast; Kamarajar Port halts container operations",
                raw_text=(
                    "Indian Meteorological Department (IMD) bulletin: Severe cyclonic storm approaching Chennai coast. "
                    "Kamarajar Port Limited (Ennore) container terminal has suspended all crane operations. "
                    "Feeder highways in Ennore logistics corridor inundated."
                ),
                timestamp=datetime.now(UTC),
                corroboration_count=3,
                confidence=0.92,
            )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0015

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.STAGE_A_PERCEPTION,
            input_summary=f"Raw feed: {event.source_feed} ({event.event_id})",
            output_summary=(
                f"Resolved primary={event.primary_entity_id}, "
                f"affected={len(event.affected_entity_ids)}, "
                f"type={event.event_type.value}, severity={event.severity}"
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )

        new_state = state.transition(
            updates={
                "event": event,
                "status": PipelineStatus.PERCEIVED,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.STAGE_A_PERCEPTION,
            success=True,
            message=(
                f"Event {event.event_id} successfully perceived and grounded into "
                f"{event.primary_entity_id} (affected={len(event.affected_entity_ids)})."
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "event_id": event.event_id,
                "primary_entity": event.primary_entity_id,
                "affected_entities": event.affected_entity_ids,
            },
        )

        return new_state, result
