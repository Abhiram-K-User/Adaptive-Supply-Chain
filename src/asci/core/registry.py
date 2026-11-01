"""
Canonical Entity Registry for South India Automotive Logistics Corridor.
Ensures unified entity IDs across Graph, Event Store, Vector Metadata, Time-Series, and Optimization plans.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class UnknownEntityError(KeyError):
    """Raised when an ungrounded entity ID is referenced."""


class CanonicalEntityRegistry:
    """
    Central authoritative registry for all entities in the corridor.
    Guarantees that Graph, Event Store, Vector Store, and Optimizers reference
    identical immutable ID strings.
    """

    def __init__(self, entities: dict[str, Entity] | None = None) -> None:
        self._entities: dict[str, Entity] = entities or {}
        self._alias_index: dict[str, str] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._alias_index.clear()
        for entity in self._entities.values():
            self._alias_index[self._normalize(entity.id)] = entity.id
            self._alias_index[self._normalize(entity.name)] = entity.id
            for alias in entity.aliases:
                self._alias_index[self._normalize(alias)] = entity.id

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip punctuation and whitespace, lowercase for gazetteer matching."""
        return re.sub(r"[^a-zA-Z0-9]", "", text).lower()

    @classmethod
    def load_from_json(cls, seed_path: str | Path | None = None) -> CanonicalEntityRegistry:
        """Load registry from JSON seed file."""
        if seed_path is None:
            # Default search path relative to module location
            candidate = (
                Path(__file__).resolve().parents[3] / "data" / "seeds" / "corridor_registry.json"
            )
            if not candidate.exists():
                # Fallback to current working directory seeds
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

    def resolve_name(self, raw_text: str) -> Entity | None:
        """
        Gazetteer resolution: resolve unstructured string or alias to a canonical Entity.
        Matches exact normalized strings first, then substring inclusion.
        """
        if not raw_text:
            return None

        normalized = self._normalize(raw_text)

        # 1. Exact alias / ID match
        if normalized in self._alias_index:
            return self._entities[self._alias_index[normalized]]

        # 2. Substring matching in registered aliases or names
        for alias_norm, entity_id in self._alias_index.items():
            if len(alias_norm) >= 4 and (alias_norm in normalized or normalized in alias_norm):
                return self._entities[entity_id]

        return None

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

