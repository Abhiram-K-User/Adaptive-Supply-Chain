"""
Immutable PipelineState and domain models using Pydantic v2.
Enforces deterministic state transitions and strict validation across pipeline operators.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DisruptionEventType(StrEnum):
    """Regional event taxonomy per Section 5.1 of PRD."""

    HAZARD_PORT = "HAZARD_PORT"
    HAZARD_ROAD = "HAZARD_ROAD"
    PORT_CONGESTION_STRIKE = "PORT_CONGESTION_STRIKE"
    RAIL_DISRUPTION = "RAIL_DISRUPTION"
    SHIPPING_SCHEDULE = "SHIPPING_SCHEDULE"
    TRADE_POLICY = "TRADE_POLICY"
    PLANT_OUTAGE = "PLANT_OUTAGE"


class EventStatus(StrEnum):
    """Disruption event lifecycle state."""

    NEW = "NEW"
    UPDATED = "UPDATED"
    MITIGATED = "MITIGATED"
    RETRACTED = "RETRACTED"
    EXPIRED = "EXPIRED"


class TrustTier(StrEnum):
    """Evidence provenance trust tier per Section 9 of PRD."""

    TIER_A = "TIER_A"  # Official authorities (e.g. IMD, Port Trust, GDACS)
    TIER_B = "TIER_B"  # Mainstream logistics & trade press (e.g. JOC, Hindu BusinessLine)
    TIER_C = "TIER_C"  # Social media / unverified operational chatter


class OperatorType(StrEnum):
    """Agentic RAG and pipeline operator identifiers per Section 6.2 of PRD."""

    STAGE_A_PERCEPTION = "STAGE_A_PERCEPTION"
    RETRIEVE_TEXT = "RETRIEVE_TEXT"
    RETRIEVE_GRAPH = "RETRIEVE_GRAPH"
    RETRIEVE_TS = "RETRIEVE_TS"
    RETRIEVE_DECISIONS = "RETRIEVE_DECISIONS"
    REWRITE_QUERY = "REWRITE_QUERY"
    GRADE = "GRADE"
    GRAPH_ANALYZE = "GRAPH_ANALYZE"
    PROPAGATE = "PROPAGATE"
    SCENARIOS = "SCENARIOS"
    OPTIMIZE = "OPTIMIZE"
    VERIFY = "VERIFY"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


class VerificationVerdict(StrEnum):
    """Outcome verdict for verification layers."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class PipelineStatus(StrEnum):
    """Overall pipeline execution lifecycle status."""

    INITIALIZED = "INITIALIZED"
    PERCEIVED = "PERCEIVED"
    ANALYZED = "ANALYZED"
    PLANNED = "PLANNED"
    VERIFIED = "VERIFIED"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Domain Sub-Models
# ---------------------------------------------------------------------------


class RawSignal(BaseModel):
    """
    Untrusted raw ingestion signal container passed into Stage A perception.
    Raw text fields remain strictly isolated from system instructions.
    """

    model_config = ConfigDict(frozen=True)

    signal_id: str
    source_feed: str
    trust_tier: TrustTier = TrustTier.TIER_B
    raw_headline: str
    raw_text: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latitude: float | None = None
    longitude: float | None = None
    polygon: list[tuple[float, float]] = Field(default_factory=list)
    source_url: str | None = None
    hint_entity_id: str | None = None
    hint_event_type: DisruptionEventType | None = None
    hint_severity: float | None = Field(default=None, ge=0.0, le=1.0)
    hint_duration_days: float | None = Field(default=None, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisruptionEvent(BaseModel):
    """Validated disruption alert record grounded in canonical registry IDs."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: DisruptionEventType
    status: EventStatus = EventStatus.NEW
    primary_entity_id: str
    affected_entity_ids: list[str] = Field(default_factory=list)
    severity: float = Field(ge=0.0, le=1.0, description="Normalized severity in [0.0, 1.0]")
    estimated_duration_days: float = Field(gt=0.0)
    source_feed: str
    raw_headline: str
    raw_text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    corroboration_count: int = Field(default=1, ge=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    spatial_footprint: list[tuple[float, float]] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    applied_plan_id: str | None = None
    mitigated_at: datetime | None = None


class PathRiskMetric(BaseModel):
    """Structural vulnerability metric for a corridor path."""

    model_config = ConfigDict(frozen=True)

    origin_id: str
    destination_id: str
    path: list[str]
    mode: str
    exposure: float = Field(ge=0.0)
    criticality: float = Field(ge=0.0)
    utilisation: float = Field(default=0.0, ge=0.0)
    uncertainty_factor: float = Field(default=1.0, ge=0.0)
    concentration: float = Field(default=1.0, ge=0.0)
    path_risk: float = Field(ge=0.0)
    baseline_delay_hrs: float = Field(ge=0.0)


class LineStopMetric(BaseModel):
    """Plant-level line-stop metric per Section 5.2 of PRD."""

    model_config = ConfigDict(frozen=True)

    plant_id: str
    days_of_cover: float
    expected_delay_days: float
    time_to_line_stop_days: float
    line_stop_risk: float = Field(ge=0.0, le=1.0)
    line_stop_probability: float = Field(default=0.0, ge=0.0, le=1.0)


class GraphContext(BaseModel):
    """Extracted impacted corridor subgraph and risk indicators."""

    model_config = ConfigDict(frozen=True)

    impacted_nodes: list[str] = Field(default_factory=list)
    impacted_edges: list[tuple[str, str]] = Field(default_factory=list)
    node_capacity_multipliers: dict[str, float] = Field(default_factory=dict)
    edge_capacity_multipliers: dict[str, float] = Field(default_factory=dict)
    k_hops: int = Field(default=2, ge=1)
    propagated_node_delays_hrs: dict[str, float] = Field(default_factory=dict)
    hop_decay_applied: bool = False
    propagation_tier: int = 1
    redistributed_edge_loads_teu: dict[str, float] = Field(default_factory=dict)
    edge_congestion_ratios: dict[str, float] = Field(default_factory=dict)
    path_metrics: list[PathRiskMetric] = Field(default_factory=list)
    line_stop_metrics: list[LineStopMetric] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """Evidence passage retrieved from vector or time-series memory."""

    model_config = ConfigDict(frozen=True)

    citation_id: str
    source: str
    trust_tier: TrustTier
    entity_ids: list[str]
    snippet: str
    publication_date: str
    supported_claims: list[str] = Field(default_factory=list)
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    region: str | None = None
    hazard_types: list[DisruptionEventType] = Field(default_factory=list)
    untrusted_quoted: bool = True
    expires_at: str | None = None


class Scenario(BaseModel):
    """Discrete disruption scenario with probability weighting."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    name: str
    probability: float = Field(gt=0.0, le=1.0)
    capacity_multipliers: dict[str, float] = Field(default_factory=dict)
    duration_days: float = Field(gt=0.0)


class FlowAllocation(BaseModel):
    """Reallocated freight flow across a corridor path."""

    model_config = ConfigDict(frozen=True)

    commodity: str = "CONTAINERISED_AUTO_PARTS"
    origin_id: str
    destination_id: str
    path: list[str]
    mode: str
    flow_teu: float = Field(ge=0.0)
    unit_cost: float = Field(ge=0.0)
    total_cost: float = Field(ge=0.0)


class MitigationPlan(BaseModel):
    """Optimized response plan specifying rerouting and mode shift."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    objective_cost: float = Field(ge=0.0)
    allocations: list[FlowAllocation] = Field(default_factory=list)
    unmet_demand_teu: float = Field(default=0.0, ge=0.0)
    mode_split: dict[str, float] = Field(default_factory=dict)
    risk_mode: str = "DETERMINISTIC"
    cvar_cost: float | None = Field(default=None, ge=0.0)
    solver_engine: str = "OR_TOOLS"
    summary: str


class VerificationCheck(BaseModel):
    """Individual verification assertion across Layers L1, L2, L3."""

    model_config = ConfigDict(frozen=True)

    layer: str  # "L1", "L2", or "L3"
    check_name: str
    verdict: VerificationVerdict
    details: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    """Aggregated verification verdict covering L1, L2, and L3."""

    model_config = ConfigDict(frozen=True)

    overall_verdict: VerificationVerdict
    passed: bool
    l1_checks: list[VerificationCheck] = Field(default_factory=list)
    l2_checks: list[VerificationCheck] = Field(default_factory=list)
    l3_checks: list[VerificationCheck] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)


class OperatorTraceItem(BaseModel):
    """Chronological execution record for an operator step."""

    model_config = ConfigDict(frozen=True)

    step_index: int
    operator_type: OperatorType
    input_summary: str
    output_summary: str
    duration_ms: float = Field(ge=0.0)
    cost: float = Field(ge=0.0)
    seed: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DashboardPayload(BaseModel):
    """Serialized UI payload tailored for React and Cytoscape.js."""

    model_config = ConfigDict(frozen=True)

    event_summary: dict[str, Any]
    geospatial_network: dict[str, Any]
    line_stop_forecast: list[dict[str, Any]]
    evidence_provenance: list[dict[str, Any]]
    mitigation_summary: dict[str, Any]
    trace_timeline: list[dict[str, Any]]
    executive_briefing: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Root Immutable Pipeline State
# ---------------------------------------------------------------------------


class PipelineState(BaseModel):
    """
    Immutable state container for the ASCI pipeline.
    Enforces deterministic transitions and tracks cumulative compute costs and operator trace.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    status: PipelineStatus = PipelineStatus.INITIALIZED
    raw_signal: RawSignal | None = None
    event: DisruptionEvent | None = None
    graph_context: GraphContext | None = None
    evidence_set: list[EvidenceItem] = Field(default_factory=list)
    scenario_set: list[Scenario] = Field(default_factory=list)
    candidate_plan: MitigationPlan | None = None
    verification_report: VerificationReport | None = None
    dashboard_payload: DashboardPayload | None = None
    trace: list[OperatorTraceItem] = Field(default_factory=list)
    step_count: int = Field(default=0, ge=0)
    compute_cost: float = Field(default=0.0, ge=0.0)

    def transition(
        self,
        updates: dict[str, Any],
        trace_item: OperatorTraceItem | None = None,
    ) -> PipelineState:
        """
        Create a new immutable PipelineState instance with deterministic updates.
        Increments step_count, accumulates compute cost, and appends the trace item.
        """
        new_data = dict(self.__dict__)
        new_data.update(updates)

        new_step_count = self.step_count + 1
        new_data["step_count"] = new_step_count

        if trace_item is not None:
            new_trace = list(self.trace) + [trace_item]
            new_data["trace"] = new_trace
            new_data["compute_cost"] = round(self.compute_cost + trace_item.cost, 6)

        return PipelineState(**new_data)

