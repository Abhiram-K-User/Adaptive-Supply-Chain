"""
Pytest fixtures and configuration for ASCI Platform testing.
Configures python path dynamically and provides initialized USKL stores.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from asci.api.main import create_app
from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    PipelineState,
    PipelineStatus,
)
from asci.uskl.event_store import SQLiteEventStore
from asci.uskl.graph_store import CorridorGraphStore
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore


@pytest.fixture(scope="session")
def registry() -> CanonicalEntityRegistry:
    """Fixture providing initialized CanonicalEntityRegistry."""
    return get_canonical_registry()


@pytest.fixture(scope="session")
def graph_store(registry: CanonicalEntityRegistry) -> CorridorGraphStore:
    """Fixture providing initialized CorridorGraphStore."""
    return CorridorGraphStore.load_from_json(registry=registry)


@pytest.fixture
def event_store(registry: CanonicalEntityRegistry) -> SQLiteEventStore:
    """Fixture providing in-memory SQLiteEventStore."""
    return SQLiteEventStore(db_path=":memory:", registry=registry)


@pytest.fixture
def vector_store(registry: CanonicalEntityRegistry) -> SemanticVectorStore:
    """Fixture providing initialized SemanticVectorStore."""
    return SemanticVectorStore(registry=registry)


@pytest.fixture
def timeseries_store(registry: CanonicalEntityRegistry) -> TimeSeriesStore:
    """Fixture providing in-memory TimeSeriesStore."""
    return TimeSeriesStore(db_path=":memory:", registry=registry)


@pytest.fixture
def sample_event(registry: CanonicalEntityRegistry) -> DisruptionEvent:
    """Fixture providing a sample disruption event at Kamarajar Port."""
    return DisruptionEvent(
        event_id="EVT_FIXTURE_MICHAUNG_001",
        event_type=DisruptionEventType.HAZARD_PORT,
        status=EventStatus.NEW,
        primary_entity_id="PORT_KAMARAJAR",
        affected_entity_ids=["PORT_KAMARAJAR", "CFS_ENNORE_LOGISTICS", "PORT_CHENNAI"],
        severity=0.85,
        estimated_duration_days=4.0,
        source_feed="IMD_GDACS_PORTWATCH",
        raw_headline="Severe Cyclone warning: Ennore Kamarajar Port halts container operations",
        raw_text="Severe cyclonic conditions disrupt container handling at Kamarajar Port; feeder roads waterlogged.",
        timestamp=datetime.now(UTC),
        corroboration_count=2,
        confidence=0.90,
    )


@pytest.fixture
def initial_state(sample_event: DisruptionEvent) -> PipelineState:
    """Fixture providing an initial immutable PipelineState."""
    return PipelineState(
        session_id="SESS_INTEGRATION_001",
        status=PipelineStatus.PERCEIVED,
        event=sample_event,
    )


@pytest.fixture
def pipeline_config() -> PipelineConfig:
    """Fixture providing standard deterministic pipeline configuration."""
    return PipelineConfig(
        lambda_cost_budget=0.05,
        max_steps=12,
        random_seed=42,
        k_hop_neighborhood=2,
    )


@pytest.fixture
def client() -> TestClient:
    """Fixture providing an isolated FastAPI TestClient per test."""
    return TestClient(create_app())

