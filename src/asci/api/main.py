"""
FastAPI REST Application for Adaptive Supply Chain Intelligence Platform.
Endpoints for event ingestion, live/replay feed polling, planning, human decisions,
evidence search, network topology, and canonical registry queries.
"""

from __future__ import annotations

import os
import random
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from asci.core.contracts import PipelineConfig
from asci.core.registry import get_canonical_registry
from asci.core.state import (
    DashboardPayload,
    DisruptionEvent,
    DisruptionEventType,
    EventStatus,
    MitigationPlan,
    PipelineState,
    PipelineStatus,
    RawSignal,
    TrustTier,
    VerificationReport,
)
from asci.ingestion import (
    GDACSAdapter,
    GDELTRSSAdapter,
    IMDWeatherAdapter,
    PortWatchAnomalyDetector,
)
from asci.stages import (
    StageAEventPerception,
    StageBCorridorRisk,
    StageCController,
    StageDOptimiserAndVerifier,
    StageEDashboard,
    WalkingSkeletonPipeline,
)
from asci.uskl.decision_store import DecisionTraceStore
from asci.uskl.event_store import SQLiteEventStore
from asci.uskl.graph_store import CorridorGraphStore
from asci.uskl.timeseries_store import TimeSeriesStore
from asci.uskl.vector_store import SemanticVectorStore

# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class IngestEventRequest(BaseModel):
    """Payload for submitting a disruption alert."""

    raw_headline: str
    raw_text: str
    source_feed: str = "MANUAL_OPERATIONAL_ALERT"
    trust_tier: TrustTier = TrustTier.TIER_B
    primary_entity_id: str | None = None
    affected_entity_ids: list[str] = Field(default_factory=list)
    event_type: DisruptionEventType | None = None
    severity: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_duration_days: float | None = Field(default=None, gt=0.0)
    latitude: float | None = None
    longitude: float | None = None


class IngestEventResponse(BaseModel):
    event_id: str
    primary_entity_id: str
    affected_entity_ids: list[str]
    event_type: DisruptionEventType
    severity: float
    confidence: float
    corroboration_count: int
    status: EventStatus


class ReplayIngestResponse(BaseModel):
    signals_collected: int
    events_persisted: int
    events: list[IngestEventResponse]


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


class RecordDecisionRequest(BaseModel):
    """Human planner feedback payload (Loop L2 Decision Memory)."""

    plan_id: str
    session_id: str
    decision: Literal["APPROVE", "EDIT", "REJECT"]
    planner_id: str = Field(min_length=1)
    comments: str = ""
    modifications: dict[str, Any] = Field(default_factory=dict)


class RecordDecisionResponse(BaseModel):
    decision_id: int
    plan_id: str
    session_id: str
    decision: str
    planner_id: str


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    """
    Create configured FastAPI app.
    Uses file-backed SQLite + JSONL persistence when `data_dir` (or env `ASCI_DATA_DIR`)
    is provided; falls back to in-memory stores for ephemeral testing.
    """
    api = FastAPI(
        title="Adaptive Supply Chain Intelligence Platform API",
        description="Agentic-RAG Decision Support for South India Automotive Logistics Corridor",
        version="2.0.0",
    )

    if data_dir is not None and str(data_dir).strip():
        base_dir = Path(data_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        event_db: str | Path = base_dir / "events.db"
        ts_db: str | Path = base_dir / "timeseries.db"
        decision_db: str | Path = base_dir / "decisions.db"
        trace_jsonl: str | Path | None = base_dir / "traces.jsonl"
    else:
        event_db = ":memory:"
        ts_db = ":memory:"
        decision_db = ":memory:"
        trace_jsonl = None

    registry = get_canonical_registry()
    event_store = SQLiteEventStore(db_path=event_db, registry=registry)
    decision_store = DecisionTraceStore(db_path=decision_db, jsonl_trace_path=trace_jsonl)
    graph_store = CorridorGraphStore.load_from_json(registry=registry)
    vector_store = SemanticVectorStore(registry=registry)
    timeseries_store = TimeSeriesStore(db_path=ts_db, registry=registry)

    stage_a = StageAEventPerception(registry=registry)
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    stage_c = StageCController(
        vector_store=vector_store, timeseries_store=timeseries_store, registry=registry
    )
    stage_d = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    stage_e = StageEDashboard(registry=registry, graph_store=graph_store)
    pipeline = WalkingSkeletonPipeline(
        stage_a=stage_a,
        stage_b=stage_b,
        stage_c=stage_c,
        stage_d=stage_d,
        stage_e=stage_e,
    )

    state_cache: dict[str, PipelineState] = {}

    @api.get("/health", tags=["System"])
    def health_check() -> dict[str, str]:
        """Health check endpoint confirming API status and corridor scope."""
        return {
            "status": "healthy",
            "corridor": "South India Automotive Logistics Corridor",
            "version": "2.0.0",
            "persistence": "sqlite_file" if data_dir else "in_memory",
        }

    @api.get("/registry", tags=["Registry"])
    def get_registry_entities() -> list[dict[str, Any]]:
        """Return all canonical entities (ports, plants, ICDs, CFSs, junctions)."""
        return [e.model_dump(mode="json") for e in registry.all_entities().values()]

    @api.get("/network", tags=["Network"])
    def get_network_summary() -> dict[str, Any]:
        """Return active corridor graph nodes and edges."""
        return {
            "node_count": len(graph_store.get_all_nodes()),
            "edge_count": len(graph_store.get_all_edges()),
            "nodes": graph_store.get_all_nodes(),
        }

    @api.get("/evidence/search", tags=["USKL"])
    def search_evidence(
        q: str = Query(..., min_length=1, description="Semantic search query"),
        entity_id: str | None = Query(default=None),
        region: str | None = Query(default=None),
        hazard_type: DisruptionEventType | None = Query(default=None),
        min_trust_tier: TrustTier | None = Query(default=None),
        limit: int = Query(default=5, ge=1, le=20),
    ) -> list[dict[str, Any]]:
        """Query tagged semantic vector memory with metadata filters."""
        entity_ids = [entity_id] if entity_id else None
        results = vector_store.query(
            query_text=q,
            entity_ids=entity_ids,
            region=region,
            hazard_type=hazard_type,
            min_trust_tier=min_trust_tier,
            limit=limit,
        )
        return [item.model_dump(mode="json") for item in results]

    @api.post(
        "/events",
        response_model=IngestEventResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Events"],
    )
    def ingest_event(req: IngestEventRequest) -> IngestEventResponse:
        """
        Ingest a disruption alert via Stage A tool-isolated perception,
        resolve canonical entities, and record with corroboration merging.
        """
        if req.primary_entity_id and not registry.validate_id(req.primary_entity_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specified primary_entity_id '{req.primary_entity_id}' does not exist in Canonical Entity Registry.",
            )

        signal = RawSignal(
            signal_id=f"SIG_{uuid.uuid4().hex[:10].upper()}",
            source_feed=req.source_feed,
            trust_tier=req.trust_tier,
            raw_headline=req.raw_headline,
            raw_text=req.raw_text,
            latitude=req.latitude,
            longitude=req.longitude,
            hint_entity_id=req.primary_entity_id,
            hint_event_type=req.event_type,
            hint_severity=req.severity,
            hint_duration_days=req.estimated_duration_days,
        )

        try:
            parsed_event = stage_a.parse_raw_signal(signal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        extra_affected = [aid for aid in req.affected_entity_ids if registry.validate_id(aid)]
        if extra_affected:
            merged_affected = list(dict.fromkeys(parsed_event.affected_entity_ids + extra_affected))
            parsed_event = parsed_event.model_copy(update={"affected_entity_ids": merged_affected})

        saved_event = event_store.upsert_with_corroboration(parsed_event)

        return IngestEventResponse(
            event_id=saved_event.event_id,
            primary_entity_id=saved_event.primary_entity_id,
            affected_entity_ids=saved_event.affected_entity_ids,
            event_type=saved_event.event_type,
            severity=saved_event.severity,
            confidence=saved_event.confidence,
            corroboration_count=saved_event.corroboration_count,
            status=saved_event.status,
        )

    @api.post("/ingest/replay", response_model=ReplayIngestResponse, tags=["Events"])
    def replay_ingestion_feeds(use_fallback: bool = True) -> ReplayIngestResponse:
        """
        Poll GDACS, GDELT/RSS, IMD Weather, and PortWatch anomaly detectors,
        run Stage A perception, and upsert grounded events into SQLiteEventStore.
        """
        adapters = [
            GDACSAdapter(),
            GDELTRSSAdapter(registry=registry),
            IMDWeatherAdapter(),
            PortWatchAnomalyDetector(timeseries_store=timeseries_store, registry=registry),
        ]

        all_signals: list[RawSignal] = []
        for adapter in adapters:
            all_signals.extend(adapter.fetch(use_fallback=use_fallback))

        persisted_by_id: dict[str, DisruptionEvent] = {}
        for sig in all_signals:
            try:
                parsed = stage_a.parse_raw_signal(sig)
            except ValueError:
                continue
            merged = event_store.upsert_with_corroboration(parsed)
            persisted_by_id[merged.event_id] = merged

        responses = [
            IngestEventResponse(
                event_id=e.event_id,
                primary_entity_id=e.primary_entity_id,
                affected_entity_ids=e.affected_entity_ids,
                event_type=e.event_type,
                severity=e.severity,
                confidence=e.confidence,
                corroboration_count=e.corroboration_count,
                status=e.status,
            )
            for e in persisted_by_id.values()
        ]

        return ReplayIngestResponse(
            signals_collected=len(all_signals),
            events_persisted=len(responses),
            events=responses,
        )

    @api.get("/events", tags=["Events"])
    def list_events(event_status: EventStatus | None = Query(default=None)) -> list[dict[str, Any]]:
        """List disruption events, optionally filtered by lifecycle status."""
        return [e.model_dump(mode="json") for e in event_store.list_events(status=event_status)]

    @api.get("/events/{event_id}", tags=["Events"])
    def get_event(event_id: str) -> dict[str, Any]:
        """Retrieve structured event by ID."""
        event = event_store.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event '{event_id}' not found.",
            )
        return event.model_dump(mode="json")

    @api.post("/events/{event_id}/plan", response_model=PlanResponse, tags=["Planning"])
    def generate_plan(event_id: str, req: GeneratePlanRequest) -> PlanResponse:
        """Execute end-to-end pipeline for an ingested disruption event."""
        event = event_store.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event '{event_id}' not found.",
            )

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

        if final_state.candidate_plan:
            decision_store.save_plan(
                plan=final_state.candidate_plan,
                session_id=session_id,
                event_id=event.event_id,
                status=final_state.status.value,
                verification=final_state.verification_report,
            )
        state_cache[session_id] = final_state
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

    @api.get("/plans/{plan_id}", tags=["Planning"])
    def get_plan(plan_id: str) -> dict[str, Any]:
        """Retrieve persisted mitigation plan."""
        plan = decision_store.get_plan(plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{plan_id}' not found.",
            )
        return plan.model_dump(mode="json")

    @api.post(
        "/decisions",
        response_model=RecordDecisionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Planning"],
    )
    def record_human_decision(req: RecordDecisionRequest) -> RecordDecisionResponse:
        """Record human planner Approve/Edit/Reject decision to Decision Memory."""
        plan = decision_store.get_plan(req.plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{req.plan_id}' not found.",
            )
        dec_id = decision_store.record_human_decision(
            plan_id=req.plan_id,
            session_id=req.session_id,
            decision=req.decision,
            planner_id=req.planner_id,
            comments=req.comments,
            modifications=req.modifications,
        )
        return RecordDecisionResponse(
            decision_id=dec_id,
            plan_id=req.plan_id,
            session_id=req.session_id,
            decision=req.decision,
            planner_id=req.planner_id,
        )

    @api.get("/traces/{session_id}", tags=["Planning"])
    def get_traces(session_id: str) -> list[dict[str, Any]]:
        """Retrieve chronological operator trace entries for a session."""
        traces = decision_store.get_traces_for_session(session_id)
        if not traces and session_id in state_cache:
            traces = [t.model_dump(mode="json") for t in state_cache[session_id].trace]
        return traces

    return api


app = create_app(os.environ.get("ASCI_DATA_DIR"))
