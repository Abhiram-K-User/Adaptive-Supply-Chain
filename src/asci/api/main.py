"""
FastAPI REST Application for Adaptive Supply Chain Intelligence Platform.
Endpoints for event ingestion, live/replay feed polling, planning, human decisions,
evidence search, network topology, and canonical registry queries.
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
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
from asci.llm import (
    LLMExtractorBackend,
    MultiProviderLLMClient,
    PlanBriefingGenerator,
    load_local_dotenv,
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
    enable_llm: bool = False
    llm_provider: Literal["auto", "groq", "gemini", "openai", "ollama", "deterministic"] | None = None


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
    mode: str = "replay"
    source_statuses: list[dict[str, Any]] = Field(default_factory=list)
    weather_telemetry: list[dict[str, Any]] = Field(default_factory=list)


class GeneratePlanRequest(BaseModel):
    """Configuration overrides for pipeline execution."""

    lambda_cost_budget: float = Field(default=0.05, ge=0.0)
    random_seed: int = Field(default=42)
    k_hop_neighborhood: int = Field(default=2, ge=1, le=4)
    risk_mode: Literal["DETERMINISTIC", "EXPECTED_COST", "CVAR"] = Field(default="EXPECTED_COST")
    cvar_alpha: float = Field(default=0.90, ge=0.5, lt=1.0)
    solver_type: Literal["OR_TOOLS", "NETWORKX"] = Field(default="OR_TOOLS")
    propagation_tier: Literal[1, 2] = Field(default=2)
    enable_llm: bool = Field(default=False)
    llm_provider: Literal["auto", "groq", "gemini", "openai", "ollama", "deterministic"] | None = None


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


def create_app(
    data_dir: str | Path | None = None,
    network_scale: str | None = None,
    llm_client: MultiProviderLLMClient | None = None,
) -> FastAPI:
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
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    resolved_scale = network_scale or os.environ.get("ASCI_NETWORK_SCALE", "v0_core")
    if resolved_scale not in ("v0_core", "v1_corridor"):
        resolved_scale = "v0_core"

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

    active_llm_client = llm_client or MultiProviderLLMClient()
    registry = get_canonical_registry(network_scale=resolved_scale)
    event_store = SQLiteEventStore(db_path=event_db, registry=registry)
    decision_store = DecisionTraceStore(db_path=decision_db, jsonl_trace_path=trace_jsonl)
    graph_store = CorridorGraphStore.load_from_json(registry=registry, network_scale=resolved_scale)
    vector_store = SemanticVectorStore(registry=registry)
    timeseries_store = TimeSeriesStore(db_path=ts_db, registry=registry)

    stage_a = StageAEventPerception(registry=registry)
    stage_b = StageBCorridorRisk(graph_store=graph_store, registry=registry)
    stage_c = StageCController(
        vector_store=vector_store, timeseries_store=timeseries_store, registry=registry
    )
    stage_d = StageDOptimiserAndVerifier(registry=registry, graph_store=graph_store)
    briefing_gen = PlanBriefingGenerator(llm_client=active_llm_client, registry=registry)
    stage_e = StageEDashboard(
        registry=registry,
        graph_store=graph_store,
        briefing_generator=briefing_gen,
    )
    pipeline = WalkingSkeletonPipeline(
        stage_a=stage_a,
        stage_b=stage_b,
        stage_c=stage_c,
        stage_d=stage_d,
        stage_e=stage_e,
    )

    state_cache: dict[str, PipelineState] = {}
    feed_status_cache: dict[str, Any] = {
        "live_feeds_enabled": os.environ.get("ASCI_LIVE_FEEDS_ENABLED", "true").strip().lower()
        not in ("0", "false", "no"),
        "poll_interval_seconds": int(
            os.environ.get("ASCI_LIVE_POLL_INTERVAL_SECONDS", "0") or "0"
        ),
        "last_polled_at": None,
        "last_mode": "unpolled",
        "source_statuses": [],
        "weather_telemetry": [],
    }
    repo_root = Path(__file__).resolve().parents[3]
    react_dist_dir = repo_root / "frontend" / "dist"
    react_index_path = react_dist_dir / "index.html"
    react_assets_dir = react_dist_dir / "assets"
    ui_html_path = Path(__file__).resolve().parent.parent / "ui" / "dashboard.html"

    if react_assets_dir.is_dir():
        api.mount("/assets", StaticFiles(directory=str(react_assets_dir)), name="frontend_assets")

    @api.get("/", response_class=HTMLResponse, include_in_schema=False)
    def serve_dashboard() -> HTMLResponse:
        """Serve the built React + TypeScript + Cytoscape.js dashboard (or fallback HTML)."""
        if react_index_path.is_file():
            return HTMLResponse(content=react_index_path.read_text(encoding="utf-8"))
        if not ui_html_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard UI asset not found.",
            )
        return HTMLResponse(content=ui_html_path.read_text(encoding="utf-8"))

    @api.get("/llm/status", tags=["System"])
    def get_llm_status(provider: str | None = None) -> dict[str, Any]:
        """Return active LLM provider readiness without exposing secrets."""
        return active_llm_client.get_status(provider_override=provider)

    @api.get("/health", tags=["System"])
    def health_check() -> dict[str, str]:
        """Health check endpoint confirming API status and corridor scope."""
        return {
            "status": "healthy",
            "corridor": "South India Automotive Logistics Corridor",
            "version": "2.0.0",
            "network_scale": resolved_scale,
            "persistence": "sqlite_file" if data_dir else "in_memory",
        }

    @api.get("/registry", tags=["Registry"])
    def get_registry_entities() -> list[dict[str, Any]]:
        """Return all canonical entities (ports, plants, ICDs, CFSs, junctions)."""
        return [e.model_dump(mode="json") for e in registry.all_entities().values()]

    @api.get("/network", tags=["Network"])
    def get_network_summary() -> dict[str, Any]:
        """Return active corridor graph nodes and edges."""
        edges_list = [
            {
                "id": f"{u}_{v}_{attrs.get('key', 'default')}",
                "source": u,
                "target": v,
                "mode": attrs.get("mode", "ROAD"),
                "distance_km": attrs.get("distance_km", 0.0),
            }
            for u, v, attrs in graph_store.get_all_edges()
        ]
        return {
            "node_count": len(graph_store.get_all_nodes()),
            "edge_count": len(edges_list),
            "nodes": graph_store.get_all_nodes(),
            "edges": edges_list,
        }

    @api.get("/evidence/search", tags=["USKL"])
    def search_evidence(
        q: Annotated[str, Query(min_length=1, description="Semantic search query")],
        entity_id: Annotated[str | None, Query()] = None,
        region: Annotated[str | None, Query()] = None,
        hazard_type: Annotated[DisruptionEventType | None, Query()] = None,
        min_trust_tier: Annotated[TrustTier | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=20)] = 5,
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

        active_stage_a = (
            StageAEventPerception(
                registry=registry,
                extractor=LLMExtractorBackend(
                    llm_client=active_llm_client,
                    provider_override=req.llm_provider,
                ),
            )
            if req.enable_llm
            else stage_a
        )

        try:
            parsed_event = active_stage_a.parse_raw_signal(signal)
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

    def _run_feed_ingestion(use_fallback: bool) -> ReplayIngestResponse:
        gdacs_adapter = GDACSAdapter()
        gdelt_adapter = GDELTRSSAdapter(registry=registry)
        weather_adapter = IMDWeatherAdapter()
        portwatch_adapter = PortWatchAnomalyDetector(
            timeseries_store=timeseries_store,
            registry=registry,
        )

        adapter_specs: list[tuple[str, Any]] = [
            ("GDACS Disasters", gdacs_adapter),
            ("GDELT / India News RSS", gdelt_adapter),
            ("IMD / Open-Meteo Weather", weather_adapter),
            ("IMF PortWatch AIS", portwatch_adapter),
        ]

        all_signals: list[RawSignal] = []
        source_statuses: list[dict[str, Any]] = []
        persisted_by_id: dict[str, DisruptionEvent] = {}

        for label, adapter in adapter_specs:
            sigs = adapter.fetch(use_fallback=use_fallback)
            all_signals.extend(sigs)
            grounded_count = 0
            for sig in sigs:
                try:
                    parsed = stage_a.parse_raw_signal(sig)
                except ValueError:
                    continue
                merged = event_store.upsert_with_corroboration(parsed)
                persisted_by_id[merged.event_id] = merged
                grounded_count += 1

            source_statuses.append(
                {
                    "source": label,
                    "fetch_mode": getattr(adapter, "last_fetch_mode", "fallback"),
                    "signals_fetched": len(sigs),
                    "corridor_events_grounded": grounded_count,
                    "fetched_at": getattr(adapter, "last_fetched_at", None),
                    "error": getattr(adapter, "last_error", None),
                }
            )

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

        run_mode = "replay" if use_fallback else "live"
        feed_status_cache["last_polled_at"] = datetime.now(UTC).isoformat()
        feed_status_cache["last_mode"] = run_mode
        feed_status_cache["source_statuses"] = source_statuses
        if weather_adapter.last_telemetry:
            feed_status_cache["weather_telemetry"] = weather_adapter.last_telemetry

        return ReplayIngestResponse(
            signals_collected=len(all_signals),
            events_persisted=len(responses),
            events=responses,
            mode=run_mode,
            source_statuses=source_statuses,
            weather_telemetry=list(feed_status_cache["weather_telemetry"]),
        )

    @api.get("/feeds/status", tags=["Events"])
    def get_feeds_status() -> dict[str, Any]:
        """Return live/replay ingestion feed status and South India weather telemetry."""
        return dict(feed_status_cache)

    @api.post("/ingest/replay", response_model=ReplayIngestResponse, tags=["Events"])
    def replay_ingestion_feeds(use_fallback: bool = True) -> ReplayIngestResponse:
        """
        Poll GDACS, GDELT/RSS, IMD/Open-Meteo Weather, and PortWatch anomaly detectors,
        run Stage A perception, and upsert grounded events into SQLiteEventStore.
        """
        return _run_feed_ingestion(use_fallback=use_fallback)

    @api.post("/ingest/live", response_model=ReplayIngestResponse, tags=["Events"])
    def poll_live_feeds() -> ReplayIngestResponse:
        """Poll live internet feeds (GDACS, GDELT/Google News RSS, Open-Meteo, PortWatch)."""
        return _run_feed_ingestion(use_fallback=False)

    @api.get("/events", tags=["Events"])
    def list_events(
        event_status: Annotated[EventStatus | None, Query()] = None,
    ) -> list[dict[str, Any]]:
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
            risk_mode=req.risk_mode,
            cvar_alpha=req.cvar_alpha,
            solver_type=req.solver_type,
            propagation_tier=req.propagation_tier,
            network_scale=resolved_scale,  # type: ignore[arg-type]
            enable_llm=req.enable_llm,
            llm_provider=req.llm_provider,
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


load_local_dotenv()
app = create_app(os.environ.get("ASCI_DATA_DIR"))
