"""
Integration Test for Walking Skeleton (Gate G1).
Tests end-to-end execution of:
Perception (Stage A) -> Corridor Graph (Stage B) -> Rule Router Controller (Stage C)
-> Optimiser & Verifier (Stage D) -> Dashboard API Stub (Stage E).
"""

import random

from fastapi.testclient import TestClient

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry
from asci.core.state import (
    FlowAllocation,
    MitigationPlan,
    PipelineState,
    PipelineStatus,
    VerificationVerdict,
)
from asci.stages import (
    StageDOptimiserAndVerifier,
    WalkingSkeletonPipeline,
)


def test_walking_skeleton_end_to_end(
    initial_state: PipelineState,
    pipeline_config: PipelineConfig,
):
    """
    Gate G1 Execution: Run all 5 stages in sequence.
    Verifies that state passes between operators immutably and all L1-L3 checks pass.
    """
    pipeline = WalkingSkeletonPipeline()
    rng = random.Random(pipeline_config.random_seed)

    final_state, operator_results = pipeline.run(
        state=initial_state,
        cfg=pipeline_config,
        rng=rng,
    )

    # 1. Verify operator execution success across all 5 stages
    assert len(operator_results) == 5
    for res in operator_results:
        assert res.success is True, f"Operator {res.operator_type} failed: {res.message}"

    # 2. Verify state status transitioned through to COMPLETED
    assert final_state.status == PipelineStatus.COMPLETED
    assert final_state.step_count == 5
    assert final_state.compute_cost > 0.0

    # 3. Verify Stage B graph context
    assert final_state.graph_context is not None
    assert len(final_state.graph_context.impacted_nodes) > 0
    assert len(final_state.graph_context.line_stop_metrics) > 0

    # 4. Verify Stage C retrieved evidence & parameterized scenarios
    assert len(final_state.evidence_set) > 0
    assert len(final_state.scenario_set) == 3

    # 5. Verify Stage D optimization & L1-L3 verification
    assert final_state.candidate_plan is not None
    assert final_state.candidate_plan.objective_cost > 0.0
    assert len(final_state.candidate_plan.allocations) >= 2

    assert final_state.verification_report is not None
    assert final_state.verification_report.passed is True
    assert final_state.verification_report.overall_verdict == VerificationVerdict.PASS
    assert len(final_state.verification_report.failed_checks) == 0

    # 6. Verify Stage E serialized dashboard payload
    assert final_state.dashboard_payload is not None
    assert "nodes" in final_state.dashboard_payload.geospatial_network
    assert "edges" in final_state.dashboard_payload.geospatial_network
    assert len(final_state.dashboard_payload.line_stop_forecast) > 0

    # 7. Verify chronological trace logging
    assert len(final_state.trace) == 5
    step_indices = [t.step_index for t in final_state.trace]
    assert step_indices == [1, 2, 3, 4, 5]


def test_walking_skeleton_determinism(
    initial_state: PipelineState,
    pipeline_config: PipelineConfig,
):
    """
    Verify that executing the pipeline twice with identical random seed yields bitwise deterministic outputs.
    """
    pipeline = WalkingSkeletonPipeline()

    state1, _ = pipeline.run(
        state=initial_state,
        cfg=pipeline_config,
        rng=random.Random(pipeline_config.random_seed),
    )
    state2, _ = pipeline.run(
        state=initial_state,
        cfg=pipeline_config,
        rng=random.Random(pipeline_config.random_seed),
    )

    assert state1.candidate_plan is not None and state2.candidate_plan is not None
    assert state1.candidate_plan.objective_cost == state2.candidate_plan.objective_cost
    assert len(state1.candidate_plan.allocations) == len(state2.candidate_plan.allocations)
    assert state1.compute_cost == state2.compute_cost


def test_verifier_catches_ungrounded_entity_fault(
    initial_state: PipelineState,
    pipeline_config: PipelineConfig,
    registry: CanonicalEntityRegistry,
):
    """
    Mutation Test (PRD Suite S4): Inject ungrounded entity in plan allocations.
    Verifies Layer 1 (L1) verifier catches the breach and rejects the plan.
    """
    optimiser = StageDOptimiserAndVerifier(registry=registry)

    # First advance state to Stage B/C so graph_context and evidence are present
    pipeline = WalkingSkeletonPipeline()
    s_a, _ = pipeline.stage_a.run(initial_state, pipeline_config, random.Random(42))
    s_b, _ = pipeline.stage_b.run(s_a, pipeline_config, random.Random(42))
    s_c, _ = pipeline.stage_c.run(s_b, pipeline_config, random.Random(42))

    # Manually inject a faulty candidate plan containing ungrounded ID
    corrupted_plan = MitigationPlan(
        plan_id="PLAN_FAULTY_CORRUPTED",
        objective_cost=50000.0,
        allocations=[
            FlowAllocation(
                commodity="CONTAINERISED_AUTO_PARTS",
                origin_id="PORT_ROTTERDAM",  # Ungrounded entity!
                destination_id="PLANT_ORAGADAM",
                path=["PORT_ROTTERDAM", "PLANT_ORAGADAM"],
                mode="ROAD",
                flow_teu=500.0,
                unit_cost=100.0,
                total_cost=50000.0,
            )
        ],
        unmet_demand_teu=0.0,
        summary="Fault injection test plan",
    )

    faulty_state = s_c.transition(updates={"candidate_plan": corrupted_plan})

    # Run Stage D verifier
    verified_state, result = optimiser.run(faulty_state, pipeline_config, random.Random(42))

    # Stage D must fail verification
    assert verified_state.verification_report is not None
    assert verified_state.verification_report.passed is False
    assert verified_state.verification_report.overall_verdict == VerificationVerdict.FAIL
    assert "L1:CANONICAL_ENTITY_GROUNDING" in verified_state.verification_report.failed_checks
    assert verified_state.status == PipelineStatus.FAILED
    assert result.success is False


def test_api_walking_skeleton_e2e(client: TestClient):
    """
    Test FastAPI REST Endpoints for Gate G1:
    POST /events -> GET /events/{id} -> POST /events/{id}/plan -> GET /plans/{id}.
    """
    # 1. Check health
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    # 2. Check canonical registry endpoint
    reg_res = client.get("/registry")
    assert reg_res.status_code == 200
    assert len(reg_res.json()) >= 15

    # 3. Check network summary endpoint
    net_res = client.get("/network")
    assert net_res.status_code == 200
    assert net_res.json()["node_count"] >= 15

    # 4. Ingest an event via natural language headline
    event_payload = {
        "raw_headline": "Severe waterlogging disrupts Kamarajar Port container terminal gates",
        "raw_text": "Monsoon downpour causes flash flooding around Ennore logistics corridor.",
        "source_feed": "TEST_GDACS_FEED",
        "event_type": "HAZARD_PORT",
        "severity": 0.80,
        "estimated_duration_days": 3.0,
    }
    create_res = client.post("/events", json=event_payload)
    assert create_res.status_code == 201
    evt_data = create_res.json()
    event_id = evt_data["event_id"]
    assert evt_data["primary_entity_id"] == "PORT_KAMARAJAR"

    # 5. Fetch ingested event
    get_evt = client.get(f"/events/{event_id}")
    assert get_evt.status_code == 200
    assert get_evt.json()["event_id"] == event_id

    # 6. Trigger Walking Skeleton Planning loop (Stage A-E)
    plan_payload = {
        "lambda_cost_budget": 0.05,
        "random_seed": 42,
        "k_hop_neighborhood": 2,
    }
    plan_res = client.post(f"/events/{event_id}/plan", json=plan_payload)
    assert plan_res.status_code == 200
    plan_data = plan_res.json()

    assert plan_data["status"] == "COMPLETED"
    assert plan_data["plan"] is not None
    assert plan_data["plan"]["objective_cost"] > 0
    assert plan_data["verification"]["passed"] is True
    assert plan_data["dashboard"] is not None
    assert plan_data["step_count"] >= 4

    plan_id = plan_data["plan"]["plan_id"]
    session_id = plan_data["session_id"]

    # 7. Fetch plan by ID
    get_plan_res = client.get(f"/plans/{plan_id}")
    assert get_plan_res.status_code == 200
    assert get_plan_res.json()["plan_id"] == plan_id

    # 8. Fetch trace by session ID
    trace_res = client.get(f"/traces/{session_id}")
    assert trace_res.status_code == 200
    assert len(trace_res.json()) >= 4
