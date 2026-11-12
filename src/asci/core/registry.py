"""
Canonical Entity Registry for South India Automotive Logistics Corridor.
Ensures unified entity IDs across Graph, Event Store, Vector Metadata, Time-Series, and Optimization plans.
Includes multi-entity gazetteer resolution, fuzzy matching, and geospatial proximity/polygon lookup.
"""

from __future__ import annotations

import json
import math
import re
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

try:
    from rapidfuzz import fuzz as _rapidfuzz
except ImportError:  # pragma: no cover - optional acceleration
    _rapidfuzz = None


class EntityType(str, Enum):
    """Canonical classification for physical and operational corridor nodes."""

    PORT = "PORT"
    PLANT = "PLANT"
    ICD = "ICD"
    CFS = "CFS"
    CORRIDOR_JUNCTION = "CORRIDOR_JUNCTION"


class Entity(BaseModel):
    """Canonical corridor entity schema."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    latitude: float
    longitude: float
    region: str
    capacity_teu_per_day: float | None = None
    days_of_cover: float | None = None
    daily_demand_teu: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityMatch(BaseModel):
    """Scored canonical entity resolution match from gazetteer or spatial query."""

    model_config = ConfigDict(frozen=True)

    entity: Entity
    score: float = Field(ge=0.0, le=1.0)
    method: Literal["EXACT", "ALIAS", "FUZZY", "GEOSPATIAL"]
    matched_span: str


class UnknownEntityError(KeyError):
    """Raised when an ungrounded entity ID is referenced."""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two (lat, lon) coordinates."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
    )
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon check where polygon points are (lat, lon)."""
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _min_distance_to_polygon_km(
    lat: float,
    lon: float,
    polygon: list[tuple[float, float]],
) -> float:
    """Approximate minimum distance in km from point (lat, lon) to polygon edges."""
    if not polygon:
        return float("inf")
    if len(polygon) == 1:
        return _haversine_km(lat, lon, polygon[0][0], polygon[0][1])

    min_dist = float("inf")
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * cos_lat

    px = lon * km_per_deg_lon
    py = lat * km_per_deg_lat

    n = len(polygon)
    for i in range(n):
        lat_a, lon_a = polygon[i]
        lat_b, lon_b = polygon[(i + 1) % n]
        ax, ay = lon_a * km_per_deg_lon, lat_a * km_per_deg_lat
        bx, by = lon_b * km_per_deg_lon, lat_b * km_per_deg_lat

        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0.0:
            dist = math.hypot(px - ax, py - ay)
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            dist = math.hypot(px - proj_x, py - proj_y)
        if dist < min_dist:
            min_dist = dist

    return min_dist


def _fuzzy_similarity(a: str, b: str) -> float:
    """Normalized string similarity in [0.0, 1.0]."""
    if not a or not b:
        return 0.0
    if _rapidfuzz is not None:
        return round(_rapidfuzz.ratio(a, b) / 100.0, 4)
    return round(SequenceMatcher(None, a, b).ratio(), 4)


class CanonicalEntityRegistry:
    """
    Central authoritative registry for all entities in the corridor.
    Guarantees that Graph, Event Store, Vector Store, and Optimizers reference
    identical immutable ID strings.
    """

    def __init__(self, entities: dict[str, Entity] | None = None) -> None:
        self._entities: dict[str, Entity] = entities or {}
        self._alias_index: dict[str, str] = {}
        self._surface_forms: list[tuple[str, str, str, str]] = []
        self._resolution_memory: dict[str, str] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._alias_index.clear()
        self._surface_forms.clear()
        for entity in self._entities.values():
            id_norm = self._normalize(entity.id)
            name_norm = self._normalize(entity.name)
            self._alias_index[id_norm] = entity.id
            self._alias_index[name_norm] = entity.id
            self._surface_forms.append((entity.id, entity.id, id_norm, "EXACT"))
            self._surface_forms.append((entity.name, entity.id, name_norm, "ALIAS"))

            for alias in entity.aliases:
                alias_norm = self._normalize(alias)
                self._alias_index[alias_norm] = entity.id
                self._surface_forms.append((alias, entity.id, alias_norm, "ALIAS"))

        # Sort longest surface forms first for deterministic matching
        self._surface_forms.sort(key=lambda item: len(item[2]), reverse=True)

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip punctuation and whitespace, lowercase for gazetteer matching."""
        return re.sub(r"[^a-zA-Z0-9]", "", text).lower()

    @staticmethod
    def _normalize_spaced(text: str) -> str:
        """Collapse punctuation to single spaces and lowercase."""
        return re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()

    @classmethod
    def load_from_json(cls, seed_path: str | Path | None = None) -> CanonicalEntityRegistry:
        """Load registry from JSON seed file."""
        if seed_path is None:
            candidate = (
                Path(__file__).resolve().parents[3] / "data" / "seeds" / "corridor_registry.json"
            )
            if not candidate.exists():
                candidate = Path.cwd() / "data" / "seeds" / "corridor_registry.json"
                if not candidate.exists():
                    candidate = Path.cwd() / "asci-core" / "data" / "seeds" / "corridor_registry.json"
            seed_path = candidate

        path_obj = Path(seed_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Corridor registry seed not found at {path_obj}")

        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)

        entities: dict[str, Entity] = {}
        for item in data.get("entities", []):
            entity = Entity(
                id=item["id"],
                name=item["name"],
                entity_type=EntityType(item["entity_type"]),
                aliases=item.get("aliases", []),
                latitude=item["latitude"],
                longitude=item["longitude"],
                region=item["region"],
                capacity_teu_per_day=item.get("capacity_teu_per_day"),
                days_of_cover=item.get("days_of_cover"),
                daily_demand_teu=item.get("daily_demand_teu"),
                metadata=item.get("metadata", {}),
            )
            entities[entity.id] = entity

        return cls(entities=entities)

    def get(self, entity_id: str) -> Entity:
        """Retrieve entity by canonical ID. Raises UnknownEntityError if not found."""
        if entity_id not in self._entities:
            raise UnknownEntityError(
                f"Entity '{entity_id}' is not registered in the Canonical Entity Registry."
            )
        return self._entities[entity_id]

    def validate_id(self, entity_id: str) -> bool:
        """Check whether an entity ID is canonical and registered."""
        return entity_id in self._entities

    def record_resolution(self, surface_form: str, entity_id: str) -> None:
        """Cache a confirmed surface-form -> canonical ID resolution."""
        if not self.validate_id(entity_id):
            raise UnknownEntityError(f"Cannot cache ungrounded entity ID '{entity_id}'.")
        norm = self._normalize(surface_form)
        if norm:
            self._resolution_memory[norm] = entity_id

    def get_cached_resolution(self, surface_form: str) -> Entity | None:
        """Look up a previously confirmed surface-form resolution."""
        norm = self._normalize(surface_form)
        entity_id = self._resolution_memory.get(norm)
        return self._entities[entity_id] if entity_id and entity_id in self._entities else None

    def resolve_entities(
        self,
        raw_text: str,
        min_score: float = 0.78,
    ) -> list[EntityMatch]:
        """
        Multi-entity gazetteer resolution across headlines or full articles.
        Combines exact ID/alias phrase matches, cached memory, and bounded fuzzy n-gram matching.
        Returns matches sorted by descending score and earliest appearance.
        """
        if not raw_text or not raw_text.strip():
            return []

        best_by_entity: dict[str, tuple[EntityMatch, int]] = {}
        spaced_text = self._normalize_spaced(raw_text)
        compact_text = self._normalize(raw_text)

        # 0. Resolution memory cache check for full compact input
        if compact_text in self._resolution_memory:
            eid = self._resolution_memory[compact_text]
            ent = self._entities[eid]
            best_by_entity[eid] = (
                EntityMatch(entity=ent, score=1.0, method="EXACT", matched_span=raw_text.strip()),
                0,
            )

        # 1. Exact ID / Name / Alias phrase matching
        for raw_form, entity_id, norm_form, method in self._surface_forms:
            if not norm_form or len(norm_form) < 3:
                continue

            # Canonical IDs must match literally as an identifier token, never across space-separated words
            if method == "EXACT":
                m_id = re.search(rf"(?<!\w){re.escape(entity_id)}(?!\w)", raw_text)
                if m_id is None:
                    continue
                match_pos = m_id.start()
                score = 1.0
                actual_method: Literal["EXACT", "ALIAS", "FUZZY", "GEOSPATIAL"] = "EXACT"
                span = entity_id
            else:
                spaced_form = self._normalize_spaced(raw_form)
                pattern = rf"(?<!\w){re.escape(spaced_form)}(?!\w)"
                m = re.search(pattern, spaced_text)
                if m is not None:
                    match_pos = m.start()
                    score = 0.96
                    actual_method = "ALIAS"
                    span = raw_form
                elif len(norm_form) >= 6 and norm_form in compact_text:
                    match_pos = compact_text.find(norm_form)
                    score = 0.92
                    actual_method = "ALIAS"
                    span = raw_form
                else:
                    continue

            candidate = EntityMatch(
                entity=self._entities[entity_id],
                score=score,
                method=actual_method,
                matched_span=span,
            )
            prev = best_by_entity.get(entity_id)
            if prev is None or candidate.score > prev[0].score or (
                candidate.score == prev[0].score and match_pos < prev[1]
            ):
                best_by_entity[entity_id] = (candidate, match_pos)

        # 2. Fuzzy n-gram matching for misspelled or noisy spans
        tokens = spaced_text.split()
        max_ngram = min(4, len(tokens))
        for n in range(1, max_ngram + 1):
            for idx in range(len(tokens) - n + 1):
                window_tokens = tokens[idx : idx + n]
                window_spaced = " ".join(window_tokens)
                window_compact = "".join(window_tokens)
                if len(window_compact) < 5:
                    continue

                for raw_form, entity_id, norm_form, method in self._surface_forms:
                    if method == "EXACT" or len(norm_form) < 5:
                        continue
                    # Skip already matched at higher confidence
                    if entity_id in best_by_entity and best_by_entity[entity_id][0].score >= 0.92:
                        continue
                    # Quick length & word-count ratio prune to prevent partial single-word false matches
                    form_words = self._normalize_spaced(raw_form).split()
                    if abs(len(form_words) - n) > 1:
                        continue
                    len_ratio = min(len(window_compact), len(norm_form)) / max(
                        len(window_compact), len(norm_form)
                    )
                    if len_ratio < 0.80:
                        continue

                    sim = max(
                        _fuzzy_similarity(window_compact, norm_form),
                        _fuzzy_similarity(window_spaced, self._normalize_spaced(raw_form)),
                    )
                    if sim >= min_score:
                        candidate = EntityMatch(
                            entity=self._entities[entity_id],
                            score=sim,
                            method="FUZZY",
                            matched_span=window_spaced,
                        )
                        prev = best_by_entity.get(entity_id)
                        if prev is None or candidate.score > prev[0].score:
                            best_by_entity[entity_id] = (candidate, idx)

        ranked = sorted(
            best_by_entity.values(),
            key=lambda item: (-item[0].score, item[1], item[0].entity.id),
        )
        return [item[0] for item in ranked]

    def resolve_name(self, raw_text: str) -> Entity | None:
        """
        Gazetteer resolution: resolve unstructured string or alias to a canonical Entity.
        Preserves backward compatibility while leveraging multi-entity & fuzzy resolution.
        """
        if not raw_text:
            return None

        normalized = self._normalize(raw_text)

        # 1. Exact alias / ID / resolution memory match
        if normalized in self._resolution_memory:
            return self._entities[self._resolution_memory[normalized]]
        if normalized in self._alias_index:
            return self._entities[self._alias_index[normalized]]

        # 2. Substring matching in registered aliases or names
        for alias_norm, entity_id in self._alias_index.items():
            if len(alias_norm) >= 4 and (alias_norm in normalized or normalized in alias_norm):
                return self._entities[entity_id]

        # 3. Fallback to full gazetteer multi-entity / fuzzy match
        matches = self.resolve_entities(raw_text, min_score=0.80)
        return matches[0].entity if matches else None

    def resolve_by_coordinates(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50.0,
    ) -> list[EntityMatch]:
        """Resolve canonical entities within radius_km of a (lat, lon) point."""
        if radius_km <= 0:
            return []

        matches: list[tuple[float, EntityMatch]] = []
        for entity in self._entities.values():
            dist = _haversine_km(lat, lon, entity.latitude, entity.longitude)
            if dist <= radius_km:
                score = round(max(0.1, 1.0 - (dist / (radius_km * 1.1))), 4)
                matches.append(
                    (
                        dist,
                        EntityMatch(
                            entity=entity,
                            score=score,
                            method="GEOSPATIAL",
                            matched_span=f"({lat:.4f},{lon:.4f})@{dist:.1f}km",
                        ),
                    )
                )

        matches.sort(key=lambda item: item[0])
        return [m for _, m in matches]

    def resolve_by_polygon(
        self,
        polygon: list[tuple[float, float]],
        buffer_km: float = 15.0,
        coords_are_lon_lat: bool = False,
    ) -> list[EntityMatch]:
        """
        Resolve canonical entities inside or within buffer_km of a geographic polygon.
        Set coords_are_lon_lat=True when passing GeoJSON [lon, lat] rings.
        """
        if len(polygon) < 3:
            return []

        lat_lon_poly = [(pt[1], pt[0]) for pt in polygon] if coords_are_lon_lat else list(polygon)

        matches: list[tuple[float, EntityMatch]] = []
        for entity in self._entities.values():
            inside = _point_in_polygon(entity.latitude, entity.longitude, lat_lon_poly)
            if inside:
                matches.append(
                    (
                        0.0,
                        EntityMatch(
                            entity=entity,
                            score=1.0,
                            method="GEOSPATIAL",
                            matched_span="POLYGON_INTERIOR",
                        ),
                    )
                )
            elif buffer_km > 0:
                dist = _min_distance_to_polygon_km(
                    entity.latitude, entity.longitude, lat_lon_poly
                )
                if dist <= buffer_km:
                    score = round(max(0.2, 0.9 - 0.7 * (dist / buffer_km)), 4)
                    matches.append(
                        (
                            dist,
                            EntityMatch(
                                entity=entity,
                                score=score,
                                method="GEOSPATIAL",
                                matched_span=f"POLYGON_BUFFER@{dist:.1f}km",
                            ),
                        )
                    )

        matches.sort(key=lambda item: (item[0], item[1].entity.id))
        return [m for _, m in matches]

    def get_by_type(self, entity_type: EntityType) -> list[Entity]:
        """Filter entities by type."""
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    def all_entities(self) -> dict[str, Entity]:
        """Return a mapping of all registered entities."""
        return dict(self._entities)

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._entities

    def __getitem__(self, entity_id: str) -> Entity:
        return self.get(entity_id)

    def __len__(self) -> int:
        return len(self._entities)


_GLOBAL_REGISTRY: CanonicalEntityRegistry | None = None


def get_canonical_registry() -> CanonicalEntityRegistry:
    """Singleton getter for the global canonical entity registry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = CanonicalEntityRegistry.load_from_json()
    return _GLOBAL_REGISTRY
