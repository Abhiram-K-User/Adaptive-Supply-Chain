# ASCI Project Context (`asci-core`)

> **Target Audience**: AI coding agents and engineering teammates (M1–M5) working on the **Adaptive Supply Chain Intelligence Platform (Integrated Agentic-RAG Edition v2.0)**.
> **Governing Specification**: [`../adaptive_supply_chain_intelligence_prd.md`](../adaptive_supply_chain_intelligence_prd.md) (resides one folder above the `asci-core` git root; ask the repo owner if missing from a standalone clone). Treat the PRD as the product contract, and **this file + `src/asci/` + `tests/` as ground truth for what is actually built**.
> **Note on `README.md`**: `README.md` still reflects the early Week 1–2 skeleton directory tree and API table; defer to this document for current architecture, status, and module boundaries.

---

## 1. Repository & Git Sync Status

* **Git Repository Root**: `asci-core/` (`origin` -> `https://github.com/Abhiram-K-User/Adaptive-Supply-Chain.git`, branch `main`).
* **Remote vs. Local State**:
  * Commit `a850535` on `origin/main` contains **only Phase 1 (W1–W2 Walking Skeleton)**.
  * Uncommitted local work inside `asci-core/` contains **Phase 2 (W3–W4: Ingestion Adapters, Gazetteer & Vector Store)**, **early Phase 3/4 pieces**, and **pre-Phase 3 bug/audit remediations** (**46/46 tests passing**).
  * Coordinate before committing/pushing so teammates pull the updated post-remediation baseline rather than branching off `a850535`.

---

## 2. Current Progress & What Has Been Implemented So Far

### Overall Progress Snapshot
* **PRD Vertical-Slice Completion (PRD Sec. 12.3 — 9 Phases)**:
  * **Complete (2 / 9)**: Phase 1 (`W1–W2`) and Phase 2 (`W3–W4`).
  * **Partially Implemented (2 / 9)**: Phase 3 (`W5–W6`, **~45%**) and Phase 4 (`W7–W8`, **~30%**).
  * **Not Started (5 / 9)**: Phases 5–9 (`W9–W14`, **0%**).
  * **Estimated Overall PRD v2.0 Completeness**: **~30%** (solid backend walking skeleton, verified ingestion/gazetteer/vector memory, real single-commodity flow solver, and L1–L3 verifier; major solver, agentic loop, frontend UI, ML policy, and benchmark suites remain).
* **Current Active Milestone**: Finish **Phase 3 (W5–W6)** hardening to clear **Gates G2 & G3** (`OR-Tools` + `SciPy HiGHS` dual-solver, `state.scenario_set` expected/CVaR optimization, 100–150 node OSMnx graph, and Suite S1–S4 fault-mutation runner).
* **Test Health**: **46 / 46 tests pass** (`38` unit tests across 8 files + `8` integration tests; `~2.6s`). CI (`ruff check src tests` + `pytest`) is configured in `.github/workflows/ci.yml` (`ruff` is not installed locally yet).

### PRD Milestone Gates (`G0–G5`) Status
| Gate | Target | Current Status | Notes |
| :--- | :--- | :--- | :--- |
| **G0 (W2)** | Data readiness & fallback adapters | **Passed** | Replay fixtures & calibrated baselines ready; live feeds work with offline fallback |
| **G1 (W2)** | End-to-end Walking Skeleton in CI | **Passed** | Stage A -> E executes deterministically via CLI & REST API (46/46 passing locally) |
| **G2 (W6)** | Reproducible Stage B + zero-breach OR-Tools baseline | **Partial** | Stage B & NetworkX split-node flow are deterministic and zero-breach on 23 nodes; OR-Tools/HiGHS & 100–150 node OSMnx graph pending |
| **G3 (W6)** | L1–L3 verifier catches `>= 99%` injected S4 faults | **Partial** | Genuine L1–L3 verification + unit S4 tests implemented; full S4 mutation benchmark harness pending |
| **G4 (W11)** | Learned masked controller + citation gate (`>= 95%`) | **Not Started** | Iterative controller, baselines, and PyTorch masked MLP not yet built |
| **G5 (W14)** | Full benchmarks & S6 backtest in one Docker command | **Not Started** | Container builds API only; benchmark/repro entrypoint not yet built |

### What Has Been Implemented So Far (Verified Functional Components)
1. **Immutable State & Contracts (`src/asci/core/`)**:
   * Frozen Pydantic v2 `PipelineState`, `.transition()` copy-on-write state updates, `PipelineConfig`, `OperatorResult`, `Operator` protocol, and domain models (`RawSignal`, `DisruptionEvent`, `GraphContext`, `EvidenceItem`, `Scenario`, `FlowAllocation`, `MitigationPlan`, `VerificationReport`, `DashboardPayload`).
2. **Canonical Entity Registry & Gazetteer (`src/asci/core/registry.py`)**:
   * Master registry of 23 entities (`27,000 TEU/day` ports, `5,300 TEU/day` plant demand) raising `UnknownEntityError` on ungrounded IDs.
   * Exact ID/alias phrase matching, cached resolution memory, bounded fuzzy n-gram matching (`difflib`, optional `rapidfuzz`), Haversine coordinate matching, and ray-casting polygon/buffer resolution (`coords_are_lon_lat` supported).
3. **USKL Persistent & Analytic Stores (`src/asci/uskl/`)**:
   * `CorridorGraphStore`: 23-node, 42-link `nx.MultiDiGraph` loader, active-edge queries, path `mode` detection (`ROAD` vs `INTERMODAL`), transit-ranked path finder, k-hop neighborhood extraction.
   * `SQLiteEventStore`: CRUD, `(primary_entity_id, event_type)` corroboration merging (`NEW -> UPDATED`), `RETRACTED` and timestamp-based `EXPIRED` lifecycle methods.
   * `SemanticVectorStore`: 8 curated SOP playbooks, deterministic offline `HashedDenseEncoder` (`hashed-concept-bow`) with logistics synonym canonicalization, optional FAISS index support, filterable search (`entity_ids`, `region`, `hazard_type`, `min_trust_tier`, `as_of_date`), and delimiter sanitization.
   * `TimeSeriesStore`: SQLite baselines (7 ports), daily PortWatch observations, empirical post-cyclone recovery curves (`PORT_KAMARAJAR`, `PORT_CHENNAI`).
   * `DecisionTraceStore`: SQLite persistence for `plans`, `operator_traces`, and `human_decisions` (`APPROVE | EDIT | REJECT`) plus append-only JSONL traces.
4. **Multimodal Ingestion & Tool-Isolated Stage A (`src/asci/ingestion/`, `stage_a_events.py`)**:
   * Adapters for **GDACS** (GeoJSON incl. `dict` URL & `MultiPolygon`), **GDELT + RSS** (RFC-2822 fallback parser), **IMD Weather**, and **IMF PortWatch** Z-score/drop anomaly detector.
   * `quote_untrusted_text()` case-insensitive `<UNTRUSTED_DOCUMENT>` escaping + `DeterministicExtractor` with injection-clause filtering, `3x` headline weighting, word-boundary scoring across all 7 `DisruptionEventType`s, and `mentioned_spans`.
5. **Stage B, C, D, E Execution & REST API (`src/asci/stages/`, `src/asci/api/main.py`)**:
   * **Stage B**: Node/edge capacity multipliers, k-hop subgraph, bottleneck path capacities, `nx.betweenness_centrality`, path `mode`, backup-corridor `LineStopMetric`s.
   * **Stage C**: Budget/step masking, deterministic `event.timestamp` vector queries, `lambda_cost_budget`-gated query broadening, duration-windowed recovery blending, 3 discrete scenarios.
   * **Stage D**: Split-node (`IN -> OUT`) + virtual parallel-edge `nx.min_cost_flow` solver (`0.1 TEU` integer scaling) across all 7 ports & 6 plants, DAG path peeling, dynamic summaries, and genuine L1–L3 verification (entity grounding, corroboration, active-edge/acyclic continuity, aggregated node/edge capacity bounds, exact flow conservation + demand reconciliation, unmet demand tolerance, entity-matched citation grounding).
   * **Stage E**: Cytoscape.js graph/edge-flow serializer preserving `FAILED` / `ESCALATED` verification statuses.
   * **FastAPI**: `create_app(data_dir)` supporting `:memory:` or `ASCI_DATA_DIR` SQLite/JSONL persistence across 12 live endpoints.

### Phase-by-Phase PRD Progress Breakdown

| PRD Phase | Timeline | Status | Implemented vs. Missing |
| :--- | :--- | :--- | :--- |
| **1. Data Readiness & Walking Skeleton (G0/G1)** | W1–W2 | **Complete (100%)** | **Done**: Registry, frozen `PipelineState`, `Operator` protocol, Stage A–E loop, FastAPI app, Dockerfile, CI.<br>**Todo**: Push latest baseline beyond `a850535`. |
| **2. Ingestion Adapters, Gazetteer & Vector Store** | W3–W4 | **Complete (100%)** | **Done**: GDACS/GDELT/IMD/PortWatch adapters, multi-entity/fuzzy/polygon gazetteer, `DeterministicExtractor`, `SemanticVectorStore`, `SQLiteEventStore` lifecycle.<br>**Todo**: Install optional `faiss-cpu`/`sentence-transformers`/`rapidfuzz`; schedule background `expire_stale_events()`. |
| **3. Path Risk, Line-Stop KPI, Benchmarks & Verifiers L1–L3 (G2/G3)** | W5–W6 | **Partial (~45%)** | **Done**: Topology-based Stage B metrics, NetworkX single-commodity min-cost flow, genuine L1–L3 verifier checks, initial S4 tests.<br>**Missing**: **OR-Tools + SciPy HiGHS dual-solver**, multi-commodity & **CVaR / scenario optimization** (Stage D currently ignores `state.scenario_set`), **100–150 node / 300–500 edge OSMnx graph**, formal **Suite S1–S4 runner**. |
| **4. Time-Series, Propagation, Scenario Builder & Dashboard v1** | W7–W8 | **Partial (~30%)** | **Done**: `TimeSeriesStore`, PortWatch baselines/recovery curves, `StageEDashboard` Cytoscape JSON serializer, `POST /decisions`, `ASCI_DATA_DIR` persistence.<br>**Missing**: `PROPAGATE` operator (hop-decay / dynamic congestion), DuckDB backend, **`POST /whatif`**, **`POST /outcomes`**, **`GET /evidence/{id}`**, **React + TypeScript + Cytoscape.js frontend**. |
| **5. Cost Profiling & Agent Baselines** | W9 | **Not Started (0%)** | **Exists**: `lambda_cost_budget` gates one rewrite check inside Stage C.<br>**Missing**: Multi-step iterative controller loop, `RETRIEVE_DECISIONS` wiring, `No-RAG` / `Fixed-RAG` / `LLM` baselines, `GRADE` cross-encoder/LLM, citation-enforced explainer. |
| **6. Oracle Trajectories & Learned Controller (G4)** | W10–W11 | **Not Started (0%)** | **Exists**: `torch 2.5.1` installed locally.<br>**Missing**: Oracle trajectory labeling, PyTorch masked MLP policy, DAgger/masking verification. |
| **7. Benchmarks, Ablations & S6 Backtests** | W12 | **Not Started (0%)** | **Exists**: `CIT_ANALOGUE_MICHAUNG_004` + seed recovery curves.<br>**Missing**: **Suite S6 Cyclone Michaung IMF PortWatch backtest** & regret/ECE/AUROC metrics. |
| **8. Live Feeds, Trace Views & S3 Red-Team** | W13 | **Not Started (0%)** | **Exists**: Live HTTP adapter methods + injection tests.<br>**Missing**: Scheduled polling worker, UI trace timeline, **Suite S3 red-team audit**. |
| **9. Code Freeze & Docker Repro (G5)** | W14 | **Not Started (0%)** | **Exists**: FastAPI `Dockerfile`.<br>**Missing**: Full solver/ML Docker image & one-command benchmark reproduction script. |

---

## 3. Domain Scope & Seeded Network Ground Truth

* **Geography**: South India Port-Hinterland Automotive Logistics Corridor (Tamil Nadu, Karnataka, Andhra Pradesh, Kerala).
* **Commodity**: Containerised automotive components (`CONTAINERISED_AUTO_PARTS`, measured in `TEU` / `TEU/day`).
* **Transport Modes**: Maritime gateway ports feeding `ROAD` and container `RAIL` (`INTERMODAL_RAIL`) links into assembly plants.
* **Canonical Seed Scale (`data/seeds/`)**:
  * **Entities (`corridor_registry.json`)**: **23 canonical entities** total:
    * **7 `PORT`s** (`27,000.0 TEU/day` aggregate nominal port capacity): `PORT_CHENNAI` (6000), `PORT_KAMARAJAR` (4500), `PORT_KRISHNAPATNAM` (4000), `PORT_KATTUPALLI` (3500), `PORT_COCHIN` (3500), `PORT_VOC` (3000), `PORT_NEW_MANGALORE` (2500).
    * **6 `PLANT`s** (`5,300.0 TEU/day` aggregate assembly demand): `PLANT_SRIPERUMBUDUR` (1500, 3.5d cover), `PLANT_ORAGADAM` (1200, 4.5d), `PLANT_HOSUR` (900, 5.0d), `PLANT_BIDADI` (800, 4.0d), `PLANT_SRICITY` (500, 6.0d), `PLANT_COIMBATORE` (400, 5.5d).
    * **3 `ICD`s**: `ICD_WHITEFIELD` (2500), `ICD_TONDIARPET` (1800), `ICD_IRUGUR` (1200).
    * **3 `CFS`s**: `CFS_CHENNAI_CENTRAL` (1500), `CFS_WHITEFIELD` (1200), `CFS_ENNORE_LOGISTICS` (1000).
    * **4 `CORRIDOR_JUNCTION`s**: `JUNCTION_KRISHNAGIRI` (6000), `JUNCTION_RANIPET` (5000), `JUNCTION_VELLORE` (5000), `JUNCTION_CHITTOOR` (3500).
  * **Graph (`corridor_graph_v0.json`)**: Directed `nx.MultiDiGraph` with **23 nodes** and **42 active directed links** (all 23 nodes connected, including eastbound NH48 return links `KRISHNAGIRI -> VELLORE -> RANIPET -> SRIPERUMBUDUR/ORAGADAM`, `ICD_TONDIARPET` outflows, and `JUNCTION_CHITTOOR` interchanges).
  * **Playbooks (`playbooks_corpus.json`)**: **8 curated evidence documents** spanning `TIER_A`, `TIER_B`, and test traps (`TIER_C` chatter + expired 2024 advisory).
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
  │ NetworkX Min-Cost Flow Solver + L1/L2/L3 Verifier         │
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
| **Entity Registry** | `CanonicalEntityRegistry` (`src/asci/core/registry.py`) | JSON + alias/fuzzy (`rapidfuzz` optional, `difflib` fallback) + Haversine/Polygon | Master source; `get()` raises `UnknownEntityError` |
| **Corridor Graph** | `CorridorGraphStore` (`src/asci/uskl/graph_store.py`) | `networkx.MultiDiGraph` loaded from JSON | `_validate_all_nodes()` rejects ungrounded node IDs |
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
   * **Never use wall-clock `datetime.now()` inside filtering, expiry, or numerical logic.** For vector expiry checks (`as_of_date`), Stage C passes `event.timestamp.strftime("%Y-%m-%d")`.
3. **Canonical Registry Single Source of Truth**:
   * Never invent ad-hoc entity strings or hardcode port/plant behavior inside solvers/stages. Add new infrastructure strictly through `data/seeds/corridor_registry.json` and `corridor_graph_v0.json`, then query `self.registry` / `self.graph_store` dynamically.
4. **Prompt Injection & Untrusted Document Isolation**:
   * Any external headline/body or indexed snippet MUST pass through `quote_untrusted_text()` (`src/asci/ingestion/base.py`), which case-insensitively neutralizes `</?UNTRUSTED_DOCUMENT>` tags.
   * `SemanticVectorStore.add_document()` also sanitizes closing delimiter tags on snippets.
   * Any future LLM extractor conforming to `ExtractorBackend` (`src/asci/stages/stage_a_events.py`) **must remain tool-isolated** (zero operational tools, strict `ExtractedEventFields` Pydantic output).
   * In `DeterministicExtractor`, imperative prompt-injection clauses are stripped *before* keyword scoring, and headlines are weighted `3.0x` vs body `1.0x`. Preserve this separation when editing Stage A.
5. **Genuine Verification & Honest Status Propagation**:
   * Never mock verification checks (`L1`–`L3`) to return `PASS`. Stage D checks aggregate edge/node flow sums across parallel allocations, exact hop balance, corridor demand reconciliation (`delivered + unmet >= total_demand`), and entity-matched evidence grounding.
   * When `verification_report.passed is False`, `StageDOptimiserAndVerifier` sets `PipelineStatus.FAILED` and `StageEDashboard` preserves `FAILED` / `ESCALATED` (never overwrite to `COMPLETED`).
6. **Current Gate G1 Cadence Constraint**:
   * `WalkingSkeletonPipeline` (`src/asci/stages/__init__.py`) executes Stages A -> E once sequentially. `tests/integration/test_walking_skeleton.py` currently asserts `len(operator_results) == 5`, `final_state.step_count == 5`, and `len(final_state.trace) == 5`.
   * When refactoring Stage C into a multi-step iterative agent loop (`RETRIEVE_*` -> `GRADE` -> `REWRITE_QUERY` -> `SCENARIOS` -> `OPTIMIZE` -> `VERIFY` -> `STOP`), update both `WalkingSkeletonPipeline` and Gate G1 assertions intentionally together.

---

## 6. Verified Directory Layout

```text
asci-core/
├── .github/workflows/ci.yml             # Ruff lint + seed smoke checks + PyTest (Gate G1)
├── Dockerfile                           # Python 3.11-slim FastAPI image (non-root `asci` user)
├── pyproject.toml                       # Build config, pytest pythonpath=["src"], ruff rules
├── requirements.txt                     # Core runtime deps (pydantic, networkx, numpy, fastapi, uvicorn, httpx, pytest)
├── project_context.md                   # This agent context & handoff guide
├── data/
│   ├── feeds/                           # Replay fixtures: gdacs_alerts_sample.json, gdelt_news_sample.json,
│   │                                    # imd_bulletins_sample.json, portwatch_daily_sample.csv
│   └── seeds/
│       ├── corridor_registry.json       # 23 canonical entities (ports, plants, ICDs, CFSs, junctions)
│       ├── corridor_graph_v0.json       # 23-node, 42-link directed multigraph seed
│       └── playbooks_corpus.json        # 8 Tier A/B/C/expired disaster & diversion SOPs
├── src/asci/
│   ├── core/
│   │   ├── contracts.py                 # PipelineConfig, OperatorResult, Operator Protocol
│   │   ├── registry.py                  # CanonicalEntityRegistry, gazetteer fuzzy + coordinate + polygon resolution
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
│   │   ├── graph_store.py               # CorridorGraphStore wrapper + active-edge / path-mode / ranked-path helpers
│   │   ├── timeseries_store.py          # Port baselines, daily observations, hazard recovery curves
│   │   └── vector_store.py              # HashedDenseEncoder (`hashed-concept-bow`) + FAISS/NumPy filterable search
│   ├── stages/
│   │   ├── __init__.py                  # WalkingSkeletonPipeline (sequential Stage A->E runner)
│   │   ├── stage_a_events.py            # ExtractedEventFields, DeterministicExtractor, gazetteer+spatial grounding
│   │   ├── stage_b_graph.py             # k-hop subgraph, PathRiskMetric, backup-corridor LineStopMetric
│   │   ├── stage_c_controller.py        # Mask checks, vector query/rewrite, TS windowing, 3 scenarios
│   │   ├── stage_d_optimiser.py         # NetworkX split-node min_cost_flow + DAG path peeling + L1/L2/L3 verifier
│   │   └── stage_e_dashboard.py         # Cytoscape.js nodes/edges/flows + Verification/Status preservation
│   ├── api/
│   │   └── main.py                      # create_app(data_dir) factory + module-level `app` via ASCI_DATA_DIR
│   └── utils/logging.py                 # Structured JSON logger
└── tests/
    ├── conftest.py                      # Fixtures (isolated per-test TestClient(create_app()))
    ├── integration/test_walking_skeleton.py   # 8 E2E, determinism, replay, multi-port, persistence tests
    └── unit/                            # 38 unit tests across registry, state, events, adapters, vector, Stage B, Stage D
```

---

## 7. REST API Contract (`src/asci/api/main.py`)

* **App Instantiation**: `create_app(data_dir: str | Path | None = None)` creates isolated stores. Module-level `app = create_app(os.environ.get("ASCI_DATA_DIR"))`.
  * When `ASCI_DATA_DIR` is unset/empty -> uses SQLite `:memory:` (ideal for `TestClient` tests).
  * When `ASCI_DATA_DIR` is set -> persists `events.db`, `timeseries.db`, `decisions.db`, and `traces.jsonl` inside that directory.

| Method | Endpoint | Status | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | **Implemented** | Returns `status`, `corridor`, `version`, `persistence` (`sqlite_file` \| `in_memory`) |
| `GET` | `/registry` | **Implemented** | Returns all 23 `Entity` models |
| `GET` | `/network` | **Implemented** | Returns `node_count`, `edge_count`, `nodes` |
| `GET` | `/evidence/search` | **Implemented** | Query params: `q`, `entity_id`, `region`, `hazard_type`, `min_trust_tier`, `limit` |
| `POST` | `/events` | **Implemented** | `201 Created`; runs `StageAEventPerception` + `upsert_with_corroboration()` (`400` bad hint ID, `422` unresolvable entity) |
| `POST` | `/ingest/replay` | **Implemented** | Polls GDACS, GDELT/RSS, IMD, PortWatch (`use_fallback=True` default) + upserts events |
| `GET` | `/events` | **Implemented** | Optional `event_status` filter |
| `GET` | `/events/{event_id}` | **Implemented** | `404` if missing |
| `POST` | `/events/{event_id}/plan` | **Implemented** | Runs `WalkingSkeletonPipeline`, persists plan to SQLite `plans` + trace to `DecisionTraceStore` |
| `GET` | `/plans/{plan_id}` | **Implemented** | Loads persisted `MitigationPlan` from SQLite |
| `POST` | `/decisions` | **Implemented** | `201 Created`; validates `plan_id` exists (`404`), logs `APPROVE \| EDIT \| REJECT` to `human_decisions` |
| `GET` | `/traces/{session_id}` | **Implemented** | Queries `DecisionTraceStore`, falls back to in-memory `state_cache` |
| `GET` | `/evidence/{id}` | **Planned (PRD 10.2)** | Fetch single evidence item by `citation_id` |
| `POST` | `/whatif` | **Planned (PRD 10.2)** | Interactive sensitivity sandbox over custom multipliers/durations |
| `POST` | `/outcomes` | **Planned (PRD 10.2)** | Realized port throughput ingestion (Feedback Loop L1) |

---

## 8. Team Ownership & Agent Handoff Matrix (PRD Sec. 12.1)

To avoid merge conflicts across parallel branches, keep changes aligned with these module lanes:

| Lead | Scope & Files | Immediate Next Deliverables |
| :--- | :--- | :--- |
| **M1 — Agent Core & RAG** | `src/asci/stages/stage_c_controller.py`, query rewriters, evidence graders, explainers, baselines | Split monolithic Stage C step into iterative tool-calling loop (`RETRIEVE_TEXT` / `RETRIEVE_TS` / `RETRIEVE_DECISIONS` -> `GRADE` -> `REWRITE_QUERY` -> `SCENARIOS` -> `OPTIMIZE` -> `VERIFY`); implement `No-RAG` / `Fixed-RAG` / `LLM` baselines & citation-checked explanation engine; upgrade later to PyTorch masked MLP (Gate G4) |
| **M2 — Graph & Optimization** | `src/asci/stages/stage_b_graph.py`, `stage_d_optimiser.py`, `corridor_graph_v0.json`, propagation | Integrate `OR-Tools` + `SciPy HiGHS` dual-solver L2 cross-check; wire `state.scenario_set` into **expected-cost & CVaR risk-aware optimization**; implement `PROPAGATE` hop-decay / dynamic congestion simulator; scale network toward PRD target (100–150 nodes via OSMnx) |
| **M3 — Data & Integration** | `src/asci/core/registry.py`, `src/asci/ingestion/`, `src/asci/uskl/`, `stage_a_events.py`, `src/asci/api/main.py` | Implement `/whatif`, `/outcomes` (Loop L1 graph/curve update), `/evidence/{id}`; optional DuckDB & `faiss-cpu`/`sentence-transformers` integration keeping deterministic offline fallbacks working; LLM `ExtractorBackend` adapter over `quote_untrusted_text()` |
| **M4 — Frontend & Viz** | `src/asci/stages/stage_e_dashboard.py` + new React/TypeScript/Cytoscape.js UI (`frontend/` or `web/`) | Build React + TypeScript + Cytoscape.js command center consuming `/network`, `/events`, `/events/{id}/plan`, `/decisions`, `/traces/{id}`, `/whatif`; preserve Stage E payload backwards compatibility |
| **M5 — QA, Eval & Delivery** | `tests/`, `.github/workflows/ci.yml`, `Dockerfile`, benchmark runner (`benchmarks/` or `scripts/`) | Build Suites **S1–S4** + S4 fault-mutation harness (`>= 99%` catch rate for **Gate G3**), **S3** prompt-injection suite, **S6** Cyclone Michaung PortWatch backtest, and Gate G5 Docker one-command runner |

**Interface Coordination Rule**: Changes to `src/asci/core/state.py` (`PipelineState` / Pydantic schemas), `src/asci/core/contracts.py`, or `data/seeds/corridor_registry.json` affect **all 5 tracks** — treat schema changes carefully, keep defaults backward-compatible where possible, and run the full test suite before opening PRs.

---

## 9. Developer Environment, Quirks & Verification Commands

### Environment & Installed Package Reality
* **Python**: `3.11+` (`pyproject.toml` requires `>=3.11`).
* **Installed locally on current dev machine**: `pydantic 2.12.5`, `fastapi 0.162.0`, `networkx 3.6.1`, `numpy 2.3.5`, `httpx 0.28.1`, `pytest 9.1.1`, `torch 2.5.1`.
* **NOT yet installed locally (and NOT in `requirements.txt` yet)**: `ortools`, `scipy`, `faiss-cpu`, `sentence-transformers`, `rapidfuzz`, `duckdb`, `ruff`.
  * Code must either keep clean fallback paths (as `registry.py` and `vector_store.py` already do) OR update `requirements.txt`, `pyproject.toml`, and `Dockerfile` when introducing hard dependencies.
* **`PYTHONPATH` Gotcha**:
  * `pytest` automatically adds `src` via `pyproject.toml` (`pythonpath = ["src"]`).
  * Standalone `python -c ...` inside `asci-core` requires either `pip install -e .` OR `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`).

### Verification & Run Commands (from `asci-core/`)

```bash
# Run full test suite (46 tests: 38 unit + 8 integration)
pytest tests/ -v --durations=10

# Lint check enforced in GitHub Actions CI (.github/workflows/ci.yml)
# Ruff config: E, F, I, B, C4, UP (ignores E501, line-length=110, py311)
ruff check src tests

# Seed & graph integrity smoke check (matches CI)
PYTHONPATH=src python -c "from asci.core.registry import get_canonical_registry; reg = get_canonical_registry(); print(f'Loaded {len(reg)} entities')"
PYTHONPATH=src python -c "from asci.uskl.graph_store import CorridorGraphStore; gs = CorridorGraphStore.load_from_json(); print(f'Nodes={len(gs.get_all_nodes())}, Edges={len(gs.get_all_edges())}')"

# Run FastAPI backend with persistent SQLite + JSONL traces
ASCI_DATA_DIR=./local_data PYTHONPATH=src uvicorn asci.api.main:app --reload --host 0.0.0.0 --port 8000

# Docker build & run
docker build -t asci-core:2.0.0 .
docker run -p 8000:8000 -e ASCI_DATA_DIR=/app/data_runtime asci-core:2.0.0
```
