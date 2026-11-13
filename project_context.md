# ASCI Project Context (`asci-core`)

> **Target Audience**: AI coding agents and engineering teammates (M1–M5) working on the **Adaptive Supply Chain Intelligence Platform (Integrated Agentic-RAG Edition v2.0)**.
> **Governing Specification**: [`../adaptive_supply_chain_intelligence_prd.md`](../adaptive_supply_chain_intelligence_prd.md) (resides one folder above the `asci-core` git root; ask the repo owner if missing from a standalone clone). Treat the PRD as the product contract, and **this file + `src/asci/` + `tests/` as ground truth for what is actually built**.
> **Note on `README.md`**: `README.md` still reflects the early Week 1–2 skeleton directory tree and API table; defer to this document for current architecture, status, and module boundaries.

---

## 1. Repository & Git Sync Status

* **Git Repository Root**: `asci-core/` (`origin` -> `https://github.com/Abhiram-K-User/Adaptive-Supply-Chain.git`, branch `main`).
* **Repository State**:
  * **Phases 1–6 Complete (`Gates G0–G4 Passed`) & Phase 7 Active (`~77%` PRD Roadmap Complete)**:
    * **Phase 5 (`Gate G3`)**: L3 `LINE_STOP_SAFETY_THRESHOLD`, `PLAN_CHURN_LIMIT`, claim-level citation validation, and 20+ S4 fault-mutation tests (`tests/unit/test_gate_g3_fault_mutations.py`).
    * **Phase 6 (`Gate G4`)**: Tool-isolated LLM extraction & grounded explainer (`src/asci/llm/`), multi-step iterative Stage C `agentic_rag` loop + `RETRIEVE_DECISIONS`, oracle trajectory generator (`src/asci/policy/oracle.py`), and PyTorch `MaskedMLPPolicy` (`src/asci/policy/model.py`, `train_mlp_controller.py`, `learned_mlp` controller mode).
    * **Phase 7 (`Loops L1–L4` & Industrial Control Tower UI)**: `POST /whatif`, `POST /outcomes`, `GET /evidence/{id}`, `GET /decisions`, `POST /events/{event_id}/mitigate`, `POST /events/{event_id}/reopen`, `EventStatus.MITIGATED` lifecycle, Loop L4 `index_validated_decision_playbook()`, and React + TypeScript + Cytoscape.js Control Tower (`frontend/`) with `NodeDetailDrawer`, commodity-differentiated forecasting curves, and live risk/corridor map sync.

---

## 2. Current Progress & What Has Been Implemented So Far

### Overall Progress Snapshot
* **PRD Vertical-Slice Completion (9-Phase Roadmap in `TASKS.md`)**:
  * **Complete (6 / 9)**: Phases 1–6 (`G0`, `G1`, `G2`, `G3`, `G4` all **PASSED**).
  * **Active (1 / 9)**: Phase 7 (`11 / 12` tasks complete — Loops L1–L4, What-If sandbox, Evidence/Recovery UI, `NodeDetailDrawer`, and mitigation lifecycle implemented; Trace deep-dive visualizer remaining).
  * **Remaining (2 / 9)**: Phase 8 (Benchmark Suites S2, S3, S5, S6 & Ablations — S1 & S4 complete) and Phase 9 (Final Audit / Gate G5 Docker repro).
  * **Estimated Overall Completeness**: **~77%** (`47 / 65` tracked tasks in `TASKS.md`).
* **Current Active Milestone**: **Gate G5 Readiness** (Phase 7 trace deep-dive visualizer + Phase 8 Suites S2/S3/S5/S6 & ablations + Docker one-command benchmark repro).
* **Test & Build Health**: **139 / 139 tests passing** (`96` unit tests across `16` files + `43` integration tests across `3` files), `ruff check src tests scripts` clean, and `frontend` production bundle (`tsc -b && vite build`) verified.

### PRD Milestone Gates (`G0–G5`) Status
| Gate | Target | Current Status | Notes |
| :--- | :--- | :--- | :--- |
| **G0 (W2)** | Data readiness & fallback adapters | **Passed** | Replay fixtures, live HTTP-to-replay failover across all 4 adapters, & exact seed totals verified |
| **G1 (W2)** | End-to-end Walking Skeleton in CI | **Passed** | Stage A -> E executes deterministically via CLI & REST API (same-second plan non-collision + SQLite/JSONL verified) |
| **G2 (W6)** | Reproducible Stage B + zero-breach OR-Tools baseline | **Passed** | Stage B `Utilisation`/`Uncertainty`/`Concentration`/line-stop prob + Tier-1 & Tier-2 BPR `PROPAGATE`; `v1_corridor` (118 nodes / 364 links) clears all 3 v0 bottlenecks (`0.0` unmet TEU); OR-Tools GLOP + SciPy HiGHS (`< 0.1%` gap), multi-commodity, Expected-Cost/CVaR, Hypothesis fuzzing, & Suite S1 runner all verified |
| **G3 (W6)** | L1–L3 verifier catches `>= 99%` injected S4 faults | **Passed** | `L2:DUAL_SOLVER_AGREEMENT`, `LINE_STOP_SAFETY_THRESHOLD`, `PLAN_CHURN_LIMIT`, claim-level citation checks, & 20+ S4 fault-mutation tests verified |
| **G4 (W11)** | Learned masked controller + citation gate (`>= 95%`) | **Passed** | Iterative `agentic_rag` Stage C loop, `src/asci/llm/` grounded explainer, oracle trajectories (`oracle.py`), & PyTorch `MaskedMLPPolicy` (`learned_mlp`) verified in `test_learned_policy.py` |
| **G5 (W14)** | Full benchmarks & S6 backtest in one Docker command | **Pending Final Audit** | Suite S1 & S4 complete; Suites S2, S3, S5, S6 (Cyclone Michaung backtest), ablations, & Docker one-command repro pending |

### What Has Been Implemented So Far (Verified Functional Components)
1. **Immutable State & Contracts (`src/asci/core/`)**:
   * Frozen Pydantic v2 `PipelineState`, `.transition()` copy-on-write state updates, `PipelineConfig`, `OperatorResult`, `Operator` protocol, and domain models (`RawSignal`, `DisruptionEvent`, `GraphContext`, `EvidenceItem`, `Scenario`, `FlowAllocation`, `MitigationPlan`, `VerificationReport`, `DashboardPayload`).
2. **Canonical Entity Registry & Gazetteer (`src/asci/core/registry.py`)**:
   * Dual-scale master registry supporting `v0_core` (`23` entities: `27,000 TEU/day` ports, `5,300 TEU/day` plant demand) and `v1_corridor` (`118` entities: `29,500 TEU/day` ports, `12,470 TEU/day` plant demand), raising `UnknownEntityError` on ungrounded IDs.
   * Exact ID/alias phrase matching, cached resolution memory, bounded fuzzy n-gram matching (`difflib`, optional `rapidfuzz`), Haversine coordinate matching, and ray-casting polygon/buffer resolution (`coords_are_lon_lat` supported).
3. **USKL Persistent & Analytic Stores (`src/asci/uskl/`)**:
   * `CorridorGraphStore` (`src/asci/uskl/graph_store.py`) + `CorridorOSMnxBuilder` (`src/asci/uskl/osmnx_builder.py`): Dual-scale `v0_core` (`23` nodes / `42` links) & `v1_corridor` (`118` nodes / `364` links) loader, active-edge queries, path `mode` detection (`ROAD` vs `INTERMODAL`), topology-fingerprinted Yen `find_ranked_paths` cache, optional live OSMnx calibration hook, k-hop extraction.
   * `SQLiteEventStore`: CRUD, `(primary_entity_id, event_type)` corroboration merging (`NEW -> UPDATED`), `RETRACTED` and timestamp-based `EXPIRED` lifecycle methods.
   * `SemanticVectorStore`: 9 curated SOP playbooks (covering all 4 corridor states incl. Andhra Pradesh / Sri City), deterministic offline `HashedDenseEncoder` (`hashed-concept-bow`) with logistics synonym canonicalization, optional FAISS index support, filterable search (`entity_ids`, `region`, `hazard_type`, `min_trust_tier`, `as_of_date`), and delimiter sanitization.
   * `TimeSeriesStore`: SQLite baselines dynamically seeded across all `PORT`s in the active registry (`7` on `v0_core`, `8` on `v1_corridor`), daily PortWatch observations, empirical post-cyclone recovery curves (`PORT_KAMARAJAR`, `PORT_CHENNAI`).
   * `DecisionTraceStore`: SQLite persistence for `plans`, `operator_traces`, and `human_decisions` (`APPROVE | EDIT | REJECT`) plus append-only JSONL traces.
4. **Multimodal Ingestion & Tool-Isolated Stage A (`src/asci/ingestion/`, `stage_a_events.py`)**:
   * Adapters for **GDACS** (GeoJSON incl. `dict` URL & `MultiPolygon`), **GDELT + RSS** (RFC-2822 fallback parser), **IMD Weather**, and **IMF PortWatch** Z-score/drop anomaly detector.
   * `quote_untrusted_text()` case-insensitive `<UNTRUSTED_DOCUMENT>` escaping + `DeterministicExtractor` with injection-clause filtering, `3x` headline weighting, word-boundary scoring across all 7 `DisruptionEventType`s, and `mentioned_spans`.
5. **Stage B, C, D, E Execution & REST API (`src/asci/stages/`, `src/asci/api/main.py`)**:
   * **Stage B & Tier-1/Tier-2 `PROPAGATE`**: Node/edge capacity multipliers, Tier-1 k-hop BFS hop-decay & Tier-2 BPR dynamic congestion load redistribution (`stage_b_propagate.py`), bottleneck capacities, node+edge betweenness, path `mode`, full `Utilisation`/`Uncertainty`/`Concentration` risk factors, scenario `line_stop_probability`.
   * **Stage C**: Budget/step masking, deterministic `event.timestamp` vector queries, `lambda_cost_budget`-gated query broadening, duration-windowed recovery blending, 3 discrete scenarios.
   * **Stage D**: Deterministic SHA-1 `plan_id`, **Google OR-Tools (`GLOP`) primary LP + independent SciPy HiGHS dual-solver verification**, multi-commodity cargo (`POWERTRAIN_CKD`, `EV_BATTERY_PACKS`, `BODY_CHASSIS_PARTS`), JIT plant line-stop penalties, two-stage `state.scenario_set` `EXPECTED_COST`/`CVAR` optimization (`NETWORKX` optional fallback), DAG path peeling, and L1–L3 verification (incl. `L2:DUAL_SOLVER_AGREEMENT`, per-commodity demand conservation).
   * **Stage E**: Cytoscape.js graph/edge-flow serializer preserving `FAILED` / `ESCALATED` verification statuses.
   * **Benchmarks & CLI**: Statistical `SuiteS1Runner` (`src/asci/benchmarks/suite_s1.py`) and `scripts/run_suite_s1.py` auditing reproducibility, zero L1/L2 breaches, dual-solver gap, Tier-1/2 spillover, CVaR hedging, and bottleneck elimination across `v0_core` & `v1_corridor`.
   * **FastAPI & Frontend (`frontend/`)**: `create_app(data_dir, network_scale)` supports `:memory:` / `ASCI_DATA_DIR` persistence and `ASCI_NETWORK_SCALE` (`v0_core` | `v1_corridor`) across live endpoints, paired with the React + TypeScript + Cytoscape.js Control Tower (`frontend/`) featuring `NodeDetailDrawer` node-click inspection, disruption mitigation/reopen actions, Stage C telemetry, commodity-differentiated forecasting curves, What-If sandbox, and Evidence/Outcomes panels.

### Phase-by-Phase Roadmap Progress (`TASKS.md`)

| Phase | Status | Implemented vs. Remaining |
| :--- | :--- | :--- |
| **1–4. Core, Ingestion, Stage B/C/D/E & Graph Scaling (G0–G2)** | **Complete (100%)** | Registry (`v0_core` / `v1_corridor`), immutable `PipelineState`, GDACS/GDELT/IMD/PortWatch adapters, `SemanticVectorStore`, `TimeSeriesStore`, `DecisionTraceStore`, Tier-1 & Tier-2 `PROPAGATE`, OR-Tools + HiGHS dual LP, CVaR/Expected-Cost, `StageEDashboard`. |
| **5. Verifier L1–L3 Hardening (Gate G3)** | **Complete (100%)** | `LINE_STOP_SAFETY_THRESHOLD`, `PLAN_CHURN_LIMIT`, claim-level citation support checks, and 20+ S4 fault-mutation tests (`test_gate_g3_fault_mutations.py`). |
| **6. Agentic RAG & Learned Masked Policy (Gate G4)** | **Complete (100%)** | `src/asci/llm/` (`client.py`, `stage_a_llm.py`, `explainer.py`), iterative Stage C `agentic_rag` + `RETRIEVE_DECISIONS`, `src/asci/policy/` (`oracle.py`, `model.py` `MaskedMLPPolicy`, `train_mlp_controller.py`), `controller_mode` selector. |
| **7. Closed Feedback Loops & Control Tower UI** | **Active (11 / 12)** | **Done**: `POST /outcomes` (L1), `GET/POST /decisions` (L2), `POST /whatif`, `GET /evidence/{id}`, `POST /events/{id}/mitigate` & `/reopen` (`MITIGATED` lifecycle), Loop L4 `index_validated_decision_playbook()`, React/TS Enterprise UI (`frontend/`) + `NodeDetailDrawer`.<br>**Remaining**: Trace deep-dive visualizer in `TraceView.tsx`. |
| **8. Benchmark Suites (S1–S6) & Ablations** | **Partial (2 / 16)** | **Done**: Suite S1 (`suite_s1.py`) & Suite S4 (`test_gate_g3_fault_mutations.py`).<br>**Remaining**: Suites S2, S3, S5, S6 (Cyclone Michaung backtest) & 9 ablations. |
| **9. Hardening, Live Ops & Release (Gate G5)** | **Partial (2 / 5)** | **Done**: `Dockerfile` & CI (`.github/workflows/ci.yml`).<br>**Remaining**: Live polling scheduler, DuckDB/FAISS opt-in integration, one-command Docker benchmark repro. |

---

## 3. Domain Scope & Seeded Network Ground Truth

* **Geography**: South India Port-Hinterland Automotive Logistics Corridor (Tamil Nadu, Karnataka, Andhra Pradesh, Kerala).
* **Commodity**: Containerised automotive components (`POWERTRAIN_CKD`, `EV_BATTERY_PACKS`, `BODY_CHASSIS_PARTS` multi-commodity by default, or legacy single-commodity `CONTAINERISED_AUTO_PARTS`, measured in `TEU` / `TEU/day`).
* **Transport Modes**: Maritime gateway ports feeding `ROAD` and container `RAIL` (`INTERMODAL_RAIL`) links into assembly plants.
* **Canonical Seed Scales (`data/seeds/`)**:
  * **Default Core (`v0_core`)**:
    * **Entities (`corridor_registry.json`)**: **23 canonical entities** (`7` `PORT`s = `27,000.0 TEU/day`, `6` `PLANT`s = `5,300.0 TEU/day`, `3` `ICD`s, `3` `CFS`s, `4` `CORRIDOR_JUNCTION`s).
    * **Graph (`corridor_graph_v0.json`)**: Directed `nx.MultiDiGraph` with **23 nodes** and **42 active directed links**.
  * **Scaled Gate G2 Network (`v1_corridor`, selectable via `PipelineConfig.network_scale="v1_corridor"` or `ASCI_NETWORK_SCALE=v1_corridor`)**:
    * **Entities (`corridor_registry_v1.json`)**: **118 canonical entities** preserving all 23 v0 entities verbatim (`8` `PORT`s incl. `PORT_KARAIKAL` = `29,500.0 TEU/day`, `6` `ICD`s, `30` `PLANT`s = `12,470.0 TEU/day`, `22` `CFS`s, `52` `CORRIDOR_JUNCTION`s incl. `10` tagged `role="outbound_gateway"`).
    * **Graph (`corridor_graph_v1.json`)**: Directed `nx.MultiDiGraph` with **118 nodes** and **364 active directed links** generated deterministically by `CorridorOSMnxBuilder` (`src/asci/uskl/osmnx_builder.py`), eliminating all 3 v0 single-point bottlenecks.
  * **Playbooks (`playbooks_corpus.json`)**: **9 curated evidence documents** spanning `TIER_A`, `TIER_B`, and test traps (`TIER_C` chatter + expired 2024 advisory), covering all 4 corridor states (`CIT_AP_SRICITY_009` covers Andhra Pradesh / Sri City / Krishnapatnam / Chittoor).
  * **Feed Replay Fixtures (`data/feeds/`)**: Sample payloads for GDACS, GDELT/RSS, IMD weather bulletins, and IMF PortWatch CSV daily arrivals.
* **Event Taxonomy (`DisruptionEventType`)**: `HAZARD_PORT`, `HAZARD_ROAD`, `PORT_CONGESTION_STRIKE`, `RAIL_DISRUPTION`, `SHIPPING_SCHEDULE`, `TRADE_POLICY`, `PLANT_OUTAGE`.

---

## 4. Architecture & Unified State & Knowledge Layer (USKL)

All five pipeline stages and five stores share immutable canonical string identifiers enforced by `CanonicalEntityRegistry`:

```text
  [External Feeds / Manual Alerts]
                 │
                 ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage A (stage_a_events.py)                               │
  │ Untrusted Quoting -> Zero-Tool Extractor -> Gazetteer     │
  └──────────────────────────┬────────────────────────────────┘
                             │ DisruptionEvent (Canonical IDs)
                             ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage B (stage_b_graph.py)                                │
  │ k-hop Subgraph -> Topology Exposures -> Time-to-Line-Stop │
  └──────────────────────────┬────────────────────────────────┘
                             │ GraphContext
                             ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage C (stage_c_controller.py)                           │
  │ Vector Retrieval + Budget Rewrite + TS Recovery Scenarios │
  └──────────────────────────┬────────────────────────────────┘
                             │ EvidenceItem[] + Scenario[]
                             ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage D (stage_d_optimiser.py)                            │
  │ OR-Tools + HiGHS Dual LP Solver + L1/L2/L3 Verifier       │
  └──────────────────────────┬────────────────────────────────┘
                             │ MitigationPlan + VerificationReport
                             ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage E (stage_e_dashboard.py)                            │
  │ Cytoscape.js Graph/Flow Serializer + Decision Memory API  │
  └───────────────────────────────────────────────────────────┘
```

| USKL Store | Class & File | Current Backend | Canonical Validation |
| :--- | :--- | :--- | :--- |
| **Entity Registry** | `CanonicalEntityRegistry` (`src/asci/core/registry.py`) | JSON (`v0_core`/`v1_corridor`) + alias/fuzzy (`rapidfuzz` optional, `difflib` fallback) + Haversine/Polygon | Master source; `get()` raises `UnknownEntityError` |
| **Corridor Graph** | `CorridorGraphStore` (`src/asci/uskl/graph_store.py`) + `CorridorOSMnxBuilder` | `networkx.MultiDiGraph` (`v0_core`: 23/42; `v1_corridor`: 118/364) + cached Yen k-paths | `_validate_all_nodes()` rejects ungrounded node IDs |
| **Event Store** | `SQLiteEventStore` (`src/asci/uskl/event_store.py`) | SQLite (`disruption_events`) + corroboration merge | `_validate_event_entities()` checks primary + affected IDs |
| **Vector Memory** | `SemanticVectorStore` (`src/asci/uskl/vector_store.py`) | `HashedDenseEncoder` + NumPy cosine (`faiss` optional) | Rejects docs whose `entity_ids` fail `registry.validate_id()` |
| **Time-Series** | `TimeSeriesStore` (`src/asci/uskl/timeseries_store.py`) | SQLite (`port_baselines`, `recovery_curves`, `daily_port_observations`) | Validates seeded IDs against registry |
| **Decisions & Trace** | `DecisionTraceStore` (`src/asci/uskl/decision_store.py`) | SQLite (`human_decisions`, `operator_traces`, `plans`) + optional JSONL | Validates `decision in {"APPROVE", "EDIT", "REJECT"}` |

---

## 5. Non-Negotiable Coding & Security Invariants

**Every AI agent modifying `asci-core` MUST uphold these rules:**

1. **Immutable `PipelineState` Boundary**:
   * `PipelineState` (`src/asci/core/state.py`) is `ConfigDict(frozen=True)`.
   * **Never mutate state fields in-place.** Always advance state via `state.transition(updates={...}, trace_item=...)`, which returns a new state, increments `step_count`, accumulates `compute_cost`, and appends to `trace`.
2. **Unified Operator Signature & Determinism**:
   * Every stage/operator implements `Operator.run(self, state: PipelineState, cfg: PipelineConfig, rng: random.Random) -> tuple[PipelineState, OperatorResult]`.
   * Identical `(initial_state, cfg, seed)` must produce bitwise-identical plans, costs, and traces (`test_walking_skeleton_determinism`).
   * **Never use wall-clock `datetime.now()` inside filtering, expiry, plan IDs, or numerical logic.** Stage C passes `event.timestamp.strftime("%Y-%m-%d")` for expiry checks, and Stage D hashes plan artifacts with SHA-1 (`PLAN_{event_id}_{fingerprint}`) using `timestamp=event.timestamp` so same-second `/events/{id}/plan` calls are deterministic and never collide in SQLite.
3. **Canonical Registry Single Source of Truth**:
   * Never invent ad-hoc entity strings or hardcode port/plant behavior inside solvers/stages. Add new infrastructure strictly through `data/seeds/corridor_registry*.json` and `corridor_graph_v*.json` (via `CorridorOSMnxBuilder` for v1), then query `self.registry` / `self.graph_store` dynamically.
4. **Prompt Injection & Untrusted Document Isolation**:
   * Any external headline/body or indexed snippet MUST pass through `quote_untrusted_text()` (`src/asci/ingestion/base.py`), which case-insensitively neutralizes `</?UNTRUSTED_DOCUMENT>` tags.
   * `SemanticVectorStore.add_document()` also sanitizes closing delimiter tags on snippets.
   * Any future LLM extractor conforming to `ExtractorBackend` (`src/asci/stages/stage_a_events.py`) **must remain tool-isolated** (zero operational tools, strict `ExtractedEventFields` Pydantic output).
   * In `DeterministicExtractor`, imperative prompt-injection clauses are stripped *before* keyword scoring, and headlines are weighted `3.0x` vs body `1.0x`. Preserve this separation when editing Stage A.
5. **Genuine Verification & Honest Status Propagation**:
   * Never mock verification checks (`L1`–`L3`) to return `PASS`. Stage D enforces port-only origins, plant-only sinks, per-plant demand caps, closed-plant zero-passthrough bounds, aggregate edge/node flow sums across parallel allocations, exact hop balance, exact reconciled corridor shortfall (`expected_unmet`), and entity-matched evidence grounding.
   * When `verification_report.passed is False`, `StageDOptimiserAndVerifier` sets `PipelineStatus.FAILED` and `StageEDashboard` preserves `FAILED` / `ESCALATED` (never overwrite to `COMPLETED`).
   * Note on `v0_core` vs `v1_corridor`: `ICD_WHITEFIELD`/`PLANT_BIDADI`, `ICD_IRUGUR`/`PLANT_COIMBATORE`, and `PORT_KRISHNAPATNAM`/`PLANT_SRICITY` are single-point bottlenecks under `corridor_graph_v0.json` (kept intact as default for Gate G0/G1 compatibility), whereas `v1_corridor` (`corridor_graph_v1.json`) provides multi-homed road & intermodal rail redundancy clearing all three at `0.0 TEU` unmet demand under `85%` disruption.
6. **Gate G1 Cadence & Stage C Controller Modes**:
   * `WalkingSkeletonPipeline` (`src/asci/stages/__init__.py`) executes Stages A -> E sequentially in default `rule` mode (`tests/integration/test_walking_skeleton.py` asserts `len(operator_results) == 5`, `final_state.step_count == 5`, `len(final_state.trace) == 5`).
   * `PipelineConfig.controller_mode` (`"rule" | "agentic_rag" | "learned_mlp"`) enables multi-step iterative retrieval (`RETRIEVE_TEXT`, `RETRIEVE_TS`, `RETRIEVE_DECISIONS`, `GRADE`, `REWRITE_QUERY`) and PyTorch `MaskedMLPPolicy` execution while preserving deterministic `rule` mode for Gate G1 tests.

---

## 6. Verified Directory Layout

```text
asci-core/
├── .github/workflows/ci.yml             # Ruff lint + seed smoke checks + PyTest (Gate G1)
├── Dockerfile                           # Python 3.11-slim FastAPI image (non-root `asci` user)
├── pyproject.toml                       # Build config, pytest pythonpath=["src"], ruff rules
├── requirements.txt                     # Core runtime deps (pydantic, networkx, numpy, ortools, scipy, fastapi, uvicorn, httpx, pytest, hypothesis)
├── project_context.md                   # This agent context & handoff guide
├── scripts/
│   ├── run_demo.py                      # Local FastAPI + static UI launcher script
│   ├── run_suite_s1.py                  # Gate G2 Statistical Suite S1 CLI benchmark runner (--scale v0_core|v1_corridor|both)
│   └── verify_backend_frontend_connection.py # API <-> frontend integration smoke verifier
├── data/
│   ├── feeds/                           # Replay fixtures: gdacs_alerts_sample.json, gdelt_news_sample.json,
│   │                                    # imd_bulletins_sample.json, portwatch_daily_sample.csv
│   └── seeds/
│       ├── corridor_registry.json       # 23 canonical v0 entities (ports, plants, ICDs, CFSs, junctions)
│       ├── corridor_registry_v1.json    # 118 canonical v1 entities (incl. 10 outbound gateways)
│       ├── corridor_graph_v0.json       # 23-node, 42-link directed multigraph seed
│       ├── corridor_graph_v1.json       # 118-node, 364-link OSMnx-calibrated directed multigraph seed
│       └── playbooks_corpus.json        # 9 Tier A/B/C/expired disaster & diversion SOPs (adds CIT_AP_SRICITY_009)
├── src/asci/
│   ├── core/
│   │   ├── contracts.py                 # PipelineConfig (incl. propagation_tier, network_scale), OperatorResult, Operator Protocol
│   │   ├── registry.py                  # CanonicalEntityRegistry, dual-scale loader, gazetteer fuzzy + coordinate + polygon resolution
│   │   └── state.py                     # Frozen PipelineState + all Pydantic v2 domain models/enums
│   ├── ingestion/
│   │   ├── base.py                      # FeedAdapter Protocol, quote_untrusted_text(), default_feeds_dir()
│   │   ├── gdacs_adapter.py             # GDACS GeoJSON API + dict URL / MultiPolygon handling
│   │   ├── gdelt_rss_adapter.py         # GDELT Doc v2 API + RSS XML fallback (RFC-2822 timestamp parser)
│   │   ├── imd_weather_adapter.py       # IMD bulletin replay/HTTP feed
│   │   └── portwatch_detector.py        # Z-score + drop-ratio vessel/TEU anomaly detector
│   ├── uskl/
│   │   ├── decision_store.py            # SQLite human_decisions, operator_traces, plans + JSONL trace writer
│   │   ├── event_store.py               # SQLite event store + corroboration merge + expiry/retraction
│   │   ├── graph_store.py               # CorridorGraphStore + topology-fingerprinted Yen cache + active-edge / path-mode helpers
│   │   ├── osmnx_builder.py             # CorridorOSMnxBuilder (118-node / 364-link generator & live OSMnx calibration hook)
│   │   ├── timeseries_store.py          # Port baselines, daily observations, hazard recovery curves
│   │   └── vector_store.py              # HashedDenseEncoder (`hashed-concept-bow`) + FAISS/NumPy filterable search
│   ├── llm/
│   │   ├── client.py                    # LLM client & availability / status probe
│   │   ├── explainer.py                 # Grounded RAG executive briefing generator with [CIT_...] citation checks
│   │   └── stage_a_llm.py               # Tool-isolated LLM extractor backend (ExtractedEventFields)
│   ├── policy/
│   │   ├── model.py                     # PyTorch MaskedMLPPolicy & action-mask enforcement
│   │   ├── oracle.py                    # Oracle trajectory generator & regret-labeled dataset builder
│   │   └── train_mlp_controller.py      # Masked MLP training & checkpoint loader
│   ├── benchmarks/
│   │   ├── __init__.py                  # Benchmark exports
│   │   └── suite_s1.py                  # SuiteS1Runner, SuiteS1Report, SuiteS1CaseResult statistical evaluator
│   ├── stages/
│   │   ├── __init__.py                  # WalkingSkeletonPipeline (+ from_config(), optional standalone PROPAGATE)
│   │   ├── stage_a_events.py            # ExtractedEventFields, DeterministicExtractor, gazetteer+spatial grounding
│   │   ├── stage_b_graph.py             # k-hop subgraph, full PathRisk formulas, scenario LineStopMetric
│   │   ├── stage_b_propagate.py         # Tier-1 BFS hop-decay & Tier-2 BPR dynamic congestion simulators
│   │   ├── stage_c_controller.py        # rule / agentic_rag / learned_mlp controller, TS windowing, 3 scenarios
│   │   ├── stage_d_optimiser.py         # OR-Tools + HiGHS dual LP (multi-commodity, CVaR/Expected, L1-L3)
│   │   └── stage_e_dashboard.py         # Cytoscape.js nodes/edges/flows + Verification/Status preservation
│   ├── api/
│   │   └── main.py                      # create_app(data_dir, network_scale) + ASCI_DATA_DIR / ASCI_NETWORK_SCALE env support
│   └── utils/logging.py                 # Structured JSON logger
├── frontend/                            # React + TypeScript + Vite + Cytoscape.js Enterprise Control Tower
│   └── src/
│       ├── api/client.ts                # Typed REST client for FastAPI endpoints
│       ├── components/                  # CorridorMap, ForecastingView, RiskView, OptimizationView, WhatIf, Evidence, Outcomes, layout/NodeDetailDrawer.tsx
│       └── pages/                       # Overview, Network, Risk, Optimization, Forecasting, Inventory, Suppliers, Analytics
└── tests/                               # 139 tests total (96 unit across 16 files + 43 integration across 3 files)
    ├── conftest.py                      # Fixtures (isolated per-test TestClient(create_app()))
    ├── integration/
    │   ├── test_gate_g2_benchmarks.py   # 33 Gate G2 suites: 23-entity sweep, monotonicity, compound outages, 7 event taxonomies
    │   ├── test_gate_g2_suite_s1.py     # Suite S1 multi-scale benchmark gate, CLI report & v1_corridor FastAPI integration tests
    │   └── test_walking_skeleton.py     # 8 E2E, determinism, replay, multi-port, persistence tests
    └── unit/
        ├── test_demo_next_steps_api.py  # 5 tests: /whatif, /outcomes, /evidence/{id}, /decisions, Loop L1/L2 APIs
        ├── test_event_lifecycle.py      # SQLite corroboration, retraction, expiry tests
        ├── test_gate_g0_g1_contracts.py # Gate G0/G1 seed totals, live->replay failover, budget ESCALATE, same-second API non-collision
        ├── test_gate_g2_part1_solver.py # Gate G2 Part 1 tests: OR-Tools/HiGHS dual parity, multi-commodity, CVaR, JIT line-stop, NX parity
        ├── test_gate_g2_property_fuzz.py # Hypothesis property-based fuzz tests (determinism, bounds, 0.0% L1/L2 breach across v0 & v1)
        ├── test_gate_g3_fault_mutations.py # 12 Gate G3 L1-L3 fault-injection, closed-plant & Stage E status preservation tests
        ├── test_gazetteer.py            # Alias, fuzzy, spatial coordinate & polygon resolution tests
        ├── test_ingestion_adapters.py   # GDACS, GDELT/RSS, IMD, PortWatch & injection-isolation tests
        ├── test_learned_policy.py       # 6 Gate G4 tests: MaskedMLPPolicy zero masking violations & >= 95% citation support
        ├── test_llm_and_demo.py         # 11 tests: tool-isolated Stage A LLM, grounded explainer, & demo APIs
        ├── test_phase4_components.py    # TimeSeriesStore, DecisionTraceStore, Stage C budget/expiry, Cytoscape serialization tests
        ├── test_registry.py             # Canonical registry contract & UnknownEntityError tests
        ├── test_stage_b_graph.py        # Stage B bottleneck, betweenness, Tier-2 congestion & v1_corridor/OSMnx builder tests
        ├── test_stage_d_verifier.py     # Stage D solver feasibility & L1-L3 unit checks
        ├── test_state.py                # Frozen PipelineState copy-on-write transition tests
        └── test_vector_store.py         # SemanticVectorStore filter, expiry & HashedDenseEncoder tests
```

---

## 7. REST API Contract (`src/asci/api/main.py`)

* **App Instantiation**: `create_app(data_dir: str | Path | None = None, network_scale: str | None = None)` creates isolated stores. Module-level `app = create_app(os.environ.get("ASCI_DATA_DIR"), network_scale=os.environ.get("ASCI_NETWORK_SCALE"))`.
  * When `ASCI_DATA_DIR` is unset/empty -> uses SQLite `:memory:` (ideal for `TestClient` tests).
  * When `ASCI_DATA_DIR` is set -> persists `events.db`, `timeseries.db`, `decisions.db`, and `traces.jsonl` inside that directory.
  * When `ASCI_NETWORK_SCALE` is `"v1_corridor"` -> loads the 118-node / 364-edge scaled network (default `"v0_core"`).

| Method | Endpoint | Status | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | **Implemented** | Returns `status`, `corridor`, `version`, `persistence` (`sqlite_file` \| `in_memory`) |
| `GET` | `/registry` | **Implemented** | Returns all canonical `Entity` models for active `network_scale` (`23` v0 / `118` v1) |
| `GET` | `/network` | **Implemented** | Returns `node_count`, `edge_count`, `nodes` |
| `GET` | `/evidence/search` | **Implemented** | Query params: `q`, `entity_id`, `region`, `hazard_type`, `min_trust_tier`, `limit` |
| `POST` | `/events` | **Implemented** | `201 Created`; runs `StageAEventPerception` + `upsert_with_corroboration()` (`400` bad hint ID, `422` unresolvable entity) |
| `POST` | `/ingest/replay` | **Implemented** | Polls GDACS, GDELT/RSS, IMD, PortWatch (`use_fallback=True` default) + upserts events |
| `GET` | `/events` | **Implemented** | Optional `event_status` filter |
| `GET` | `/events/{event_id}` | **Implemented** | `404` if missing |
| `POST` | `/events/{event_id}/plan` | **Implemented** | Runs `WalkingSkeletonPipeline` (supports `propagation_tier`, `risk_mode`, `solver_type`), persists plan + trace |
| `GET` | `/plans/{plan_id}` | **Implemented** | Loads persisted `MitigationPlan` from SQLite |
| `POST` | `/decisions` | **Implemented** | `201 Created`; validates `plan_id` (`404`), logs `APPROVE \| EDIT \| REJECT`, indexes Loop L4 playbook, and mitigates event on `APPROVE` |
| `GET` | `/decisions` | **Implemented** | Returns persisted human decision memory audit log |
| `POST` | `/events/{event_id}/mitigate` | **Implemented** | Applies mitigation plan, logs decision/L4 playbook, and transitions event to `MITIGATED` |
| `POST` | `/events/{event_id}/reopen` | **Implemented** | Reopens a `MITIGATED` or `RETRACTED` disruption back to active `UPDATED` status |
| `GET` | `/traces/{session_id}` | **Implemented** | Queries `DecisionTraceStore`, falls back to in-memory `state_cache` |
| `GET` | `/evidence/{id}` | **Implemented** | Fetch single evidence item by `citation_id` with provenance & recovery curves |
| `POST` | `/whatif` | **Implemented** | Interactive sensitivity sandbox over custom capacity multipliers & durations |
| `POST` | `/outcomes` | **Implemented** | Realized port throughput ingestion (Feedback Loop L1 recovery recalibration) |
| `GET` | `/llm/status` | **Implemented** | Reports active LLM extractor/explainer availability |

---

## 8. Team Ownership & Agent Handoff Matrix (PRD Sec. 12.1)

To avoid merge conflicts across parallel branches, keep changes aligned with these module lanes:

| Lead | Scope & Files | Immediate Next Deliverables |
| :--- | :--- | :--- |
| **M1 — Agent Core & RAG** | `src/asci/stages/stage_c_controller.py`, query rewriters, evidence graders, explainers, baselines | Split monolithic Stage C step into iterative tool-calling loop (`RETRIEVE_TEXT` / `RETRIEVE_TS` / `RETRIEVE_DECISIONS` -> `GRADE` -> `REWRITE_QUERY` -> `SCENARIOS` -> `OPTIMIZE` -> `VERIFY`); implement `No-RAG` / `Fixed-RAG` / `LLM` baselines & citation-checked explanation engine; upgrade later to PyTorch masked MLP (Gate G4) |
| **M2 — Graph & Optimization** | `src/asci/stages/stage_b_graph.py`, `stage_b_propagate.py`, `stage_d_optimiser.py`, `osmnx_builder.py` | Add `LINE_STOP_SAFETY_THRESHOLD` & `PLAN_CHURN_LIMIT` L3 verifier gates for Gate G3 completion |
| **M3 — Data & Integration** | `src/asci/core/registry.py`, `src/asci/ingestion/`, `src/asci/uskl/`, `stage_a_events.py`, `src/asci/api/main.py` | Implement `/whatif`, `/outcomes` (Loop L1 graph/curve update), `/evidence/{id}`; optional DuckDB & `faiss-cpu`/`sentence-transformers` integration keeping deterministic offline fallbacks working; LLM `ExtractorBackend` adapter over `quote_untrusted_text()` |
| **M4 — Frontend & Viz** | `src/asci/stages/stage_e_dashboard.py` + new React/TypeScript/Cytoscape.js UI (`frontend/` or `web/`) | Build React + TypeScript + Cytoscape.js command center consuming `/network`, `/events`, `/events/{id}/plan`, `/decisions`, `/traces/{id}`, `/whatif`; preserve Stage E payload backwards compatibility |
| **M5 — QA, Eval & Delivery** | `tests/`, `src/asci/benchmarks/`, `scripts/`, `.github/workflows/ci.yml`, `Dockerfile` | Build Suites **S2–S4** + randomized S4 fault-mutation harness (`>= 99%` catch rate for **Gate G3**), **S3** prompt-injection suite, **S6** Cyclone Michaung PortWatch backtest, and Gate G5 Docker one-command runner |

**Interface Coordination Rule**: Changes to `src/asci/core/state.py` (`PipelineState` / Pydantic schemas), `src/asci/core/contracts.py`, or `data/seeds/corridor_registry*.json` affect **all 5 tracks** — treat schema changes carefully, keep defaults backward-compatible where possible, and run the full test suite before opening PRs.

---

## 9. Developer Environment, Quirks & Verification Commands

### Environment & Installed Package Reality
* **Python**: `3.11+` (`pyproject.toml` requires `>=3.11`).
* **Installed locally on current dev machine**: `pydantic 2.12.5`, `fastapi 0.162.0`, `networkx 3.6.1`, `numpy 2.3.5`, `ortools 9.15.6755`, `scipy 1.17.1`, `httpx 0.28.1`, `pytest 9.1.1`, `hypothesis 6.170.15`, `torch 2.5.1`, `ruff 0.17.4`.
* **NOT yet installed locally (optional)**: `faiss-cpu`, `sentence-transformers`, `rapidfuzz`, `duckdb`, `osmnx` (optional `[geo]` extra; deterministic offline fallback active).
  * Code must either keep clean fallback paths (as `registry.py`, `vector_store.py`, and `osmnx_builder.py` do) OR update `requirements.txt`, `pyproject.toml`, and `Dockerfile` when introducing hard dependencies.
* **`PYTHONPATH` Gotcha**:
  * `pytest` automatically adds `src` via `pyproject.toml` (`pythonpath = ["src"]`).
  * Standalone `python -c ...` inside `asci-core` requires either `pip install -e .` OR `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`).

### Verification & Run Commands (from `asci-core/`)

```bash
# Run full test suite (139 tests: 96 unit + 43 integration)
pytest tests/ -v --durations=10

# Run Gate G2 Statistical Suite S1 across both v0_core & v1_corridor
PYTHONPATH=src python scripts/run_suite_s1.py --scale both

# Lint check enforced in GitHub Actions CI (.github/workflows/ci.yml)
# Ruff config: E, F, I, B, C4, UP (ignores E501, line-length=110, py311)
ruff check src tests scripts

# Build React + TypeScript Control Tower frontend
cd frontend && npm run build

# Seed & graph integrity smoke check (matches CI)
PYTHONPATH=src python -c "from asci.core.registry import get_canonical_registry; reg = get_canonical_registry(); print(f'Loaded {len(reg)} entities')"
PYTHONPATH=src python -c "from asci.uskl.graph_store import CorridorGraphStore; gs = CorridorGraphStore.load_from_json(); print(f'Nodes={len(gs.get_all_nodes())}, Edges={len(gs.get_all_edges())}')"
PYTHONPATH=src python -c "from asci.uskl.graph_store import CorridorGraphStore; gs = CorridorGraphStore.load_from_json(network_scale='v1_corridor'); print(f'v1 Nodes={len(gs.get_all_nodes())}, Edges={len(gs.get_all_edges())}')"

# Run FastAPI backend with persistent SQLite + JSONL traces
ASCI_DATA_DIR=./local_data PYTHONPATH=src uvicorn asci.api.main:app --reload --host 0.0.0.0 --port 8000

# Docker build & run
docker build -t asci-core:2.0.0 .
docker run -p 8000:8000 -e ASCI_DATA_DIR=/app/data_runtime asci-core:2.0.0
```
