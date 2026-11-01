"""
FastAPI REST Application for Adaptive Supply Chain Intelligence Platform.
Endpoints for event ingestion, agentic planning, network topology, and canonical registry queries.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DashboardPayload,
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    MitigationPlan,
    OperatorTraceItem,
    PipelineState,
    PipelineStatus,
    VerificationReport,
)
from asci.stages import WalkingSkeletonPipeline
from asci.uskl.decision_store import DecisionTraceStore
from asci.uskl.event_store import SQLiteEventStore
from asci.uskl.graph_store import CorridorGraphStore

app = FastAPI(
    title="Adaptive Supply Chain Intelligence Platform API",
    description="Agentic-RAG Decision Support for South India Automotive Logistics Corridor",
    version="2.0.0",
)

# Shared memory/in-process instances for the API
registry = get_canonical_registry()
event_store = SQLiteEventStore(registry=registry)
decision_store = DecisionTraceStore()
graph_store = CorridorGraphStore.load_from_json(registry=registry)
pipeline = WalkingSkeletonPipeline()

# In-memory plan cache for quick retrieval
_PLAN_CACHE: dict[str, MitigationPlan] = {}
_STATE_CACHE: dict[str, PipelineState] = {}


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class IngestEventRequest(BaseModel):
    """Payload for submitting a disruption alert."""

    raw_headline: str
    raw_text: str
    source_feed: str = "MANUAL_OPERATIONAL_ALERT"
    primary_entity_id: str | None = None
    affected_entity_ids: list[str] = Field(default_factory=list)
    event_type: DisruptionEventType = DisruptionEventType.HAZARD_PORT
    severity: float = Field(default=0.80, ge=0.0, le=1.0)
    estimated_duration_days: float = Field(default=3.0, gt=0.0)


class IngestEventResponse(BaseModel):
    event_id: str
    primary_entity_id: str
    affected_entity_ids: list[str]
    event_type: DisruptionEventType
    severity: float
    confidence: float
    status: EventStatus


class GeneratePlanRequest(BaseModel):
    """Configuration overrides for pipeline execution."""

    lambda_cost_budget: float = Field(default=0.05, ge=0.0)
    random_seed: int = Field(default=42)
    k_hop_neighborhood: int = Field(default=2, ge=1, le=4)


class PlanResponse(BaseModel):
    session_id: str
    event_id: str
    status: PipelineStatus
    plan: MitigationPlan | None
    verification: VerificationReport | None
    dashboard: DashboardPayload | None
    compute_cost: float
    step_count: int


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Health check endpoint confirming API status and corridor scope."""
    return {
        "status": "healthy",
        "corridor": "South India Automotive Logistics Corridor",
        "version": "2.0.0",
    }


@app.get("/registry", tags=["Registry"])
def get_registry_entities() -> list[dict[str, Any]]:
    """Return all canonical entities (ports, plants, ICDs, CFSs, junctions)."""
    return [e.model_dump(mode="json") for e in registry.all_entities().values()]


@app.get("/network", tags=["Network"])
def get_network_summary() -> dict[str, Any]:
    """Return active corridor graph nodes and edges."""
    return {
        "node_count": len(graph_store.get_all_nodes()),
        "edge_count": len(graph_store.get_all_edges()),
        "nodes": graph_store.get_all_nodes(),
    }


@app.post("/events", response_model=IngestEventResponse, status_code=status.HTTP_201_CREATED, tags=["Events"])
def ingest_event(req: IngestEventRequest) -> IngestEventResponse:
    """Ingest a disruption alert, resolve canonical entity, and store in event store."""
    primary_id = req.primary_entity_id
    if not primary_id:
        # Run gazetteer resolution against raw headline and text
        matched_entity = registry.resolve_name(req.raw_headline) or registry.resolve_name(req.raw_text)
        if not matched_entity:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not resolve any canonical entity from the provided headline or text.",
            )
        primary_id = matched_entity.id

    if not registry.validate_id(primary_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Specified primary_entity_id '{primary_id}' does not exist in Canonical Entity Registry.",
        )

    # Validate affected entity IDs
    validated_affected = []
    for aid in req.affected_entity_ids:
        if registry.validate_id(aid):
            validated_affected.append(aid)

    event_id = f"EVT_{uuid.uuid4().hex[:8].upper()}"
    event = DisruptionEvent(
        event_id=event_id,
        event_type=req.event_type,
        status=EventStatus.NEW,
        primary_entity_id=primary_id,
        affected_entity_ids=validated_affected,
        severity=req.severity,
        estimated_duration_days=req.estimated_duration_days,
        source_feed=req.source_feed,
        raw_headline=req.raw_headline,
        raw_text=req.raw_text,
        corroboration_count=1,
        confidence=0.88,
    )

    event_store.save_event(event)

    return IngestEventResponse(
        event_id=event.event_id,
        primary_entity_id=event.primary_entity_id,
        affected_entity_ids=event.affected_entity_ids,
        event_type=event.event_type,
        severity=event.severity,
        confidence=event.confidence,
        status=event.status,
    )


@app.get("/events/{event_id}", tags=["Events"])
def get_event(event_id: str) -> dict[str, Any]:
    """Retrieve structured event by ID."""
    event = event_store.get_event(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event '{event_id}' not found.")
    return event.model_dump(mode="json")


@app.post("/events/{event_id}/plan", response_model=PlanResponse, tags=["Planning"])
def generate_plan(event_id: str, req: GeneratePlanRequest) -> PlanResponse:
    """Execute end-to-end pipeline (Gate G1 walking skeleton) for an ingested disruption event."""
    event = event_store.get_event(event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event '{event_id}' not found.")

    session_id = f"SESS_{uuid.uuid4().hex[:8].upper()}"
    cfg = PipelineConfig(
        lambda_cost_budget=req.lambda_cost_budget,
        random_seed=req.random_seed,
        k_hop_neighborhood=req.k_hop_neighborhood,
    )
    rng = random.Random(cfg.random_seed)

    initial_state = PipelineState(
        session_id=session_id,
        status=PipelineStatus.PERCEIVED,
        event=event,
    )

    final_state, _ = pipeline.run(initial_state, cfg, rng)

    # Persist traces and plan
    if final_state.candidate_plan:
        _PLAN_CACHE[final_state.candidate_plan.plan_id] = final_state.candidate_plan
    _STATE_CACHE[session_id] = final_state
    decision_store.record_trace(session_id, final_state.trace)

    return PlanResponse(
        session_id=session_id,
        event_id=event.event_id,
        status=final_state.status,
        plan=final_state.candidate_plan,
        verification=final_state.verification_report,
        dashboard=final_state.dashboard_payload,
        compute_cost=final_state.compute_cost,
        step_count=final_state.step_count,
    )


@app.get("/plans/{plan_id}", tags=["Planning"])
def get_plan(plan_id: str) -> dict[str, Any]:
    """Retrieve generated mitigation plan."""
    if plan_id not in _PLAN_CACHE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{plan_id}' not found.")
    return _PLAN_CACHE[plan_id].model_dump(mode="json")


@app.get("/traces/{session_id}", tags=["Planning"])
def get_traces(session_id: str) -> list[dict[str, Any]]:
    """Retrieve chronological operator trace entries for a session."""
    traces = decision_store.get_traces_for_session(session_id)
    if not traces and session_id in _STATE_CACHE:
        traces = [t.model_dump(mode="json") for t in _STATE_CACHE[session_id].trace]
    return traces

