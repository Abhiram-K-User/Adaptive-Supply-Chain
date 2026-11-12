# Product Requirements Document (PRD)
## Adaptive Supply Chain Intelligence Platform (Integrated Agentic-RAG Edition)

---

## 1. Document Control & Metadata

* **Product Name**: Adaptive Supply Chain Intelligence Platform
* **Edition**: Integrated Agentic-RAG Edition (v2.0)
* **Date**: 16 October 2026 (Revises v1.0 dated 30 September 2026)
* **Target Industry**: Automotive and automotive components logistics (containerised parts, import/export)
* **Target Geography**: South India port-hinterland corridor (Karnataka, Tamil Nadu, Andhra Pradesh, Kerala)
* **Core Philosophy**: A single end-to-end pipeline operating over a Unified State & Knowledge Layer (USKL), unifying agentic retrieval, corridor risk graph modeling, and deterministic mathematical optimization under human-in-the-loop governance
* **Team Allocation**: 5 cross-functional engineering leads
* **Authoritative Reference**: *Adaptive Supply Chain Intelligence – Technical Design and Methodology Report v2.0* (39 pages)

---

## 2. Executive Summary & Problem Definition

Just-in-time (JIT) automotive assembly plants across South India operate with lean inbound inventories, holding days rather than weeks of buffer parts. When regional disruptions occur—such as Bay of Bengal cyclones, monsoon flooding, berth strikes, or highway washouts—inbound delays rapidly trigger assembly line shutdowns.

The **Adaptive Supply Chain Intelligence Platform** converts heterogeneous, multimodal disruption signals into verified, evidence-cited response plans. Rather than relying on static, disconnected analytical silos, the system coordinates:
1. **Live Event Intelligence** grounded directly into an infrastructure graph.
2. An **Agentic RAG Controller** that dynamically balances evidence gathering (text, graph, time-series) and numerical simulation under a formal computational budget.
3. **Deterministic Optimization and Multi-Layer Verification** that ensure all suggested freight rerouting plans obey physical capacity limits and citation grounding before reaching human logistics planners.

---

## 3. Scope & Corridor Definition

### 3.1 Geographic and Industrial Focus
* **Industry Focus**: Containerised automotive components (inbound components from international/domestic suppliers to assembly plants; outbound shipments to export markets).
* **Industrial Clusters**: Sriperumbudur-Oragadam (Tamil Nadu), Bengaluru-Hosur (Karnataka/Tamil Nadu), Bidadi-Harohalli (Karnataka), Sri City (Andhra Pradesh), and Coimbatore (Tamil Nadu).
* **Gateway Maritime Ports**: Chennai Port, Kamarajar (Ennore), Kattupalli, Krishnapatnam, V.O. Chidambaranar (Tuticorin), Cochin, and New Mangalore.
* **Inland Infrastructure**: Inland Container Depots (ICDs) such as Bengaluru ICD, container freight stations (CFS), and major rail/highway transit corridors.

### 3.2 Network Graph Dimensions
* **Graph Scale**: Directed multigraph $G = (V, E)$ consisting of approximately 100–150 nodes and 300–500 edges.
* **Node Breakdown**:
  * 7–8 gateway maritime ports
  * 5–6 rail terminals / inland container depots
  * 25–40 manufacturing plants or Tier-1 supplier clusters
  * 15–25 warehouse / CFS nodes
  * ~10 outbound market gateways
* **Planning Granularity**: Daily operational horizon.

### 3.3 Scope Boundaries

| Dimension | In-Scope | Out-of-Scope |
| :--- | :--- | :--- |
| **Commodities** | Containerised automotive components | Bulk commodities, roll-on/roll-off (RoRo) finished vehicles (Tier 3 stretch only) |
| **Modes** | Road freight and ICD container rail corridors | Air freight, urban last-mile delivery, maritime ocean carrier scheduling |
| **Network Tiers** | Gateway ports to Tier-1 suppliers and OEM assembly plants | Deep Tier-3+ sub-tier supplier tracing |
| **Disruptions** | Weather hazards (cyclones, floods), port strikes/congestion, rail cuts, blank sailings, policy tariffs, plant outages | Geopolitical conflict, global macroeconomic currency shifts |
| **Automation** | Decision support with cited provenance and planner sign-off | Autonomous logistics execution bypassing human dispatchers |

---

## 4. Unified State & Knowledge Layer (USKL) and Data Architecture

### 4.1 Canonical Entity Registry
All system components read from and write to a single **Unified State & Knowledge Layer (USKL)**. The stores are bound by a centralized **Canonical Entity Registry**. Every physical entity (e.g., `PORT_KAMARAJAR`, `PLANT_ORAGADAM`) shares identical, immutable identifier strings across all five backing data stores:

```
+---------------------------------------------------------------------------------+
|                         UNIFIED STATE & KNOWLEDGE LAYER (USKL)                  |
|                 Canonical Entity Registry (Consistent Node / Edge IDs)          |
+-------------------+-----------------+-----------------+------------+------------+
|   Corridor Graph  |   Event Store   |  Vector Memory  | Time-Series|  Decisions |
|   (NetworkX/SQLite|     (SQLite)    | (FAISS/Embeddings|  (DuckDB/ |   & Trace  |
|     JSON)         |                 |   Metadata)     |   SQLite)  |   (JSONL)  |
+-------------------+-----------------+-----------------+------------+------------+
```

1. **Corridor Graph Store** (NetworkX, SQLite/JSON): Network topology, physical road/rail edges, transit capacities, flow utilization, and plant inventory days-of-cover.
2. **Event Store** (SQLite): Typed disruption events, geographic polygons, and lifecycle tracking (`new`, `updated`, `retracted`, `expired`).
3. **Vector Memory** (FAISS + sentence-transformers): Disaster bulletins, news reports, and playbook mitigation logs. Every chunk is indexed with metadata tags: entity IDs, region, hazard type, and date.
4. **Time-Series Store** (DuckDB / SQLite): Port-call counts, rainfall metrics, seasonal throughput curves, and post-event recovery trajectories.
5. **Decision & Trace Memory** (SQLite + JSONL): Operator execution sequences, token/compute costs, human approvals/edits/rejections, and realized operational outcomes.

### 4.2 Data Ingestion & Calibration Matrix

| Source | Input Supplied | Role in System | Status / Fallback |
| :--- | :--- | :--- | :--- |
| **IMF PortWatch** | AIS daily port calls, trade volume estimates | Baseline throughput, anomaly-triggered events, backtesting ground truth | **Real**. Fallback: synthetic series calibrated to published figures |
| **GDACS** | Disaster alerts (cyclones, floods) with spatial footprint | Live hazard ingestion and automated spatial intersection with corridors | **Real**. Fallback: cached disaster alerts |
| **GDELT & RSS** | Global/regional logistics news and advisories | Unstructured text ingestion for extraction and vector indexing | **Real (noisy)**. Fallback: curated regional news archive |
| **Weather / IMD APIs** | Rainfall, wind velocity, official warning bulletins | Severity priors and parametric time-series retrieval | **Real**. Fallback: manual/scraped IMD bulletins |
| **OpenStreetMap (OSMnx)** | Road and rail geometries, terminal coordinates | Edge topologies, physical distances, free-flow transit times | **Real**. Primary network backbone |
| **Trade Statistics** | UN Comtrade, Ministry of Ports publications | Outbound lane demand weights, aggregate flow calibration | **Real (coarse)**. Fallback: annual published aggregates |
| **Plant Operations** | Days-of-cover, bills of materials, tier suppliers | Line-stop exposure calculations, flow constraints | **Synthetic**. Calibrated against published port container volumes |

### 4.3 Closed Architectural Feedback Loops
* **Loop L1 (Realized Outcomes $\rightarrow$ Corridor Graph)**: Realized port throughput metrics ingested after an event update node/edge capacity multipliers and recovery curves.
* **Loop L2 (Planner Actions $\rightarrow$ Decision Memory)**: Human planner edits and rejections are indexed to inform future plan-churn constraints and serve as decision precedents.
* **Loop L3 (Operator Traces $\rightarrow$ Controller Policy)**: Execution traces tagged with empirical regret and compute costs serve as training data for adaptive controller policies.
* **Loop L4 (Validated Events $\rightarrow$ Vector Memory)**: Resolved event profiles and historical responses are indexed into vector memory to expand the analogue incident library.

---

## 5. End-to-End Pipeline & Functional Specifications

```
  [Live Feeds / PortWatch / Manual Input]
                     │
                     ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage A: Live Event Intelligence & Entity Resolution    │
  └──────────────────────────┬──────────────────────────────┘
                             │ Typed Event (Registry IDs)
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage B: Corridor Risk Graph & Path Impact Engine       │
  └──────────────────────────┬──────────────────────────────┘
                             │ Path Exposure, Criticality, Time-to-Line-Stop
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage C: Agentic RAG Controller & Computation Core      │
  │          (Iterative Loop: Retrieve ⇄ Compute ⇄ Grade)   │
  └──────────────────────────┬──────────────────────────────┘
                             │ Evidence Set, Scenarios, Candidate Flow Bounds
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage D: Deterministic Optimization & Layered Verifier  │
  │          (OR-Tools Flow Solver + L1/L2/L3 Gateways)    │
  └──────────────────────────┬──────────────────────────────┘
                             │ Verified Response Plan + Provenance Trace
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage E: Operational Dashboard & Human-in-the-Loop     │
  └─────────────────────────────────────────────────────────┘
```

### 5.1 Stage A: Live Event Intelligence
Converts raw, external text and time-series signals into validated, structured disruption records grounded in canonical registry IDs.
* **Automated Ingestion**: Scheduled polling of GDACS, GDELT, and port RSS feeds. Incorporates an IMF PortWatch anomaly detector that flags significant drops in vessel arrivals below seasonal baselines.
* **Classification & Extraction**: Filters for corridor relevance. A zero-tool extraction LLM parses unstructured text into strict Pydantic v2 data models.
* **Entity Gazetteer Resolution**: Maps text place names to canonical IDs using fuzzy matching, geospatial proximities, and past resolution memories.
* **Regional Event Taxonomy**:
  1. `HAZARD_PORT`: Coastal cyclones, sea surges, or red rain warnings affecting port operations.
  2. `HAZARD_ROAD`: Flooded highways or bridge closures along freight routes.
  3. `PORT_CONGESTION_STRIKE`: Stevedore labor strikes, customs outages, berth backlogs.
  4. `RAIL_DISRUPTION`: Railway track flooding or blockages between inland container depots and ports.
  5. `SHIPPING_SCHEDULE`: Carrier blank sailings or trade-lane diversions.
  6. `TRADE_POLICY`: Tariff shifts, customs clearance rule modifications.
  7. `PLANT_OUTAGE`: Component supplier breakdown or assembly plant stoppage.

### 5.2 Stage B: Corridor Risk Graph & Path Impact Engine
Computes physical infrastructure vulnerability and inventory depletion timelines across the corridor multigraph $G = (V, E)$.
* **Impacted Subgraph**: Applies capacity multipliers ($m \in [0.0, 1.0]$) and delays to affected nodes/edges, extracting the impacted $k$-hop subgraph.
* **Path Enumeration**: Identifies all active routes between parts suppliers, ports, and automotive assembly clusters.
* **Structural Vulnerability Metrics**:
  $$\text{Exposure}(e) = \frac{\text{Baseline Flow across element } e}{\text{Total Corridor Flow}}$$
  $$\text{Criticality}(e) = \text{Betweenness}(e) \times \text{Utilisation}(e) \times \text{Demand Dependency}(e)$$
  $$\text{PathRisk}(p) = \text{Exposure} \times \text{Criticality} \times \text{Severity} \times \text{Uncertainty Factor} \times \text{Concentration}$$
* **Plant-Level Line-Stop Metric**:
  $$\text{Time-to-Line-Stop}(\text{Plant } v) = \text{Inventory Days-of-Cover}(v) - \text{Expected Inbound Delay}(v)$$
  Calculates the probability that inbound transit delays exceed available days-of-cover across all scenarios.
* **Propagation Modeling**: Tier 1 executes deterministic hop-decay propagation; Tier 2 incorporates dynamic load redistribution simulating diverted road congestion and container dwell times.

---

## 6. Stage C: Agentic RAG Computational Core

### 6.1 Architectural Principles
* **Unified Tooling**: Treats unstructured text retrieval, graph queries, time-series analysis, and numerical solvers as equivalent tools within a unified execution budget.
* **Role Separation**: Large Language Models are strictly confined to text extraction, query reformulation, qualitative grading, and explanation generation. Mathematical optimization and constraint verification remain strictly deterministic.
* **State Immutability**: All decisions execute over an immutable Pydantic state container $S_t$.

### 6.2 Tool Catalog

| Tool Identifier | Operator Type | Target Store | Description & Return Contract |
| :--- | :--- | :--- | :--- |
| `RETRIEVE_TEXT` | Retrieval | Vector Memory | Semantic vector search filtered by entity ID, hazard class, and date. Returns ranked passages with provenance IDs. |
| `RETRIEVE_GRAPH` | Retrieval | Corridor Graph | Traverses $k$-hop neighborhood. Returns structured dependency facts and node connectivity summaries. |
| `RETRIEVE_TS` | Retrieval | Time-Series | Queries historical port call throughput and precipitation. Returns empirical drop and recovery curves. |
| `RETRIEVE_DECISIONS` | Retrieval | Decision Memory | Queries past plans for similar disruption profiles. Returns prior human modifications and outcomes. |
| `REWRITE_QUERY` | Utility | LLM Engine | Reformulates failed queries with canonical aliases and technical terms. Limit: 2 rewrites per query. |
| `GRADE` | Utility | Cross-Encoder/LLM | Evaluates retrieved passage relevance and aggregates an evidence sufficiency score ($0.0$ to $1.0$). |
| `GRAPH_ANALYZE` | Computation | Network Engine | Calculates path exposures, alternative corridor capacities, and plant time-to-line-stop metrics. |
| `PROPAGATE` | Computation | Simulator | Runs hop-decay cascade or multi-commodity dynamic load-redistribution simulations. |
| `SCENARIOS` | Computation | Scenario Engine | Generates discrete, probability-weighted future states parameterized by retrieved historical analogues. |
| `OPTIMIZE` | Computation | OR-Tools / HiGHS | Formulates and solves a deterministic or risk-aware (CVaR) minimum-cost network flow problem. |
| `VERIFY` | Validation | Verifier Engine | Executes three-tiered validation (L1, L2, L3) against network flows and cited claims. Mandatory prior to `STOP`. |

### 6.3 Policy Economics & Control Loop
The controller executes a masked policy $\pi(S_t, \lambda)$ seeking to minimize total cost and operational regret:
$$\min_{\pi} J(\pi) = \mathbb{E} \left[ \text{Regret}(\text{Plan}) + \lambda \sum_{t=1}^{T} \text{Cost}(\text{Operator}_t) \right]$$

* **Execution Masking Rules**:
  * `GRAPH_ANALYZE` must run first immediately following perception.
  * `SCENARIOS` is masked until baseline graph impact and uncertainty metrics are established.
  * `OPTIMIZE` requires complete network exposure and scenario inputs.
  * `STOP` is strictly masked until `VERIFY` returns a `PASS` verdict.
  * Hitting the step budget ($T \ge 12$) or compute budget forces an immediate `ESCALATE` action.

---

## 7. Stage D: Optimization & Layered Verification

### 7.1 Mathematical Optimization Formulation
The platform formulates logistics mitigation as a multi-commodity, minimum-cost network flow problem across directed multigraph $G = (V, E)$:
$$\min \sum_{(i,j) \in E} \sum_k c_{ij}^k x_{ij}^k + \sum_{v \in \text{Plants}} P_{\text{line-stop}}(v) \cdot \max(0, \text{Delay}_v - \text{Cover}_v) + \sum_{d \in \text{Demand}} P_{\text{unmet}} \cdot u_d$$

* **Variables**: $x_{ij}^k \ge 0$, flow of component commodity $k$ across directed link $(i, j)$; $u_d \ge 0$, unmet assembly demand.
* **Constraints**:
  1. Edge flow capacity bounds: $x_{ij} \le \text{Capacity}_{ij} \times \text{Multiplier}_{ij}$
  2. Strict conservation of flow at all transshipment and terminal nodes.
  3. Assembly line demand satisfaction and safety stock preservation.
* **Risk Modes**:
  * *Deterministic*: Used for low-uncertainty, minor events.
  * *Expected-Cost*: Balances costs across a discrete set of weighted disruption scenarios.
  * *CVaR / Robust*: Minimizes the expected cost in the worst $\alpha$-percentile outcomes (tail risk protection).
* **Solvers**: Google OR-Tools acts as primary solver; SciPy HiGHS performs independent dual-solver verification.

### 7.2 Three-Layer Verification Protocol

```
Candidate Plan & Generated Explanation
                  │
                  ▼
┌────────────────────────────────────────────────────────┐
│ Layer 1 (L1): Ingestion & Graph Grounding Validation   │
│ • Schema compliance (Pydantic v2)                      │
│ • Canonical Entity ID verification                     │
│ • Source corroboration count & provenance check        │
└─────────────────────────┬──────────────────────────────┘
                          │ PASS
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2 (L2): Network Feasibility & Mathematical Solvency│
│ • Edge flow capacity bounds (x_ij <= Cap_ij * Mult_ij) │
│ • Strict flow conservation at all transit nodes        │
│ • Closed-edge zero-flow enforcement                    │
│ • Dual-solver (OR-Tools vs HiGHS) objective agreement  │
└─────────────────────────┬──────────────────────────────┘
                          │ PASS
                          ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3 (L3): Decision Sanity & Citation Verification  │
│ • Unmet assembly demand within tolerated limits        │
│ • Plant line-stop threshold safety confirmation        │
│ • Plan churn limits relative to active operations      │
│ • Citation Support: Every claim linked to valid ID     │
└─────────────────────────┬──────────────────────────────┘
                          │ PASS
                          ▼
             Release to Human Dashboard
```

Any validation failure triggers either automated parameter repair or human escalation (`ESCALATE`) accompanied by diagnostic failure logs.

---

## 8. Stage E: Operational Dashboard & Human Review

The user interface is an operational decision command center built in React and Cytoscape.js:

* **Geospatial Corridor Map**: Renders ports, terminals, highways, rail links, and manufacturing clusters. Node colors highlight disruption statuses; edge widths display current freight volume; pulsating rings indicate uncertainty.
* **Live Event Feed**: Displays active alerts, confidence scores, source counts, and PortWatch anomaly notifications.
* **Line-Stop & Risk Panel**: Highlights assemblies at risk, time-to-line-stop estimates, and critical bottlenecks.
* **Evidence Provenance Panel**: Shows retrieved news articles, bulletins, and historical time-series curves. Displays publication dates, trust tiers, and the specific claims supported.
* **Scenario & Rerouting Plan View**: Summarizes suggested slot reservations, road-to-rail shifts, and total rerouting costs. Includes diff views against active operations.
* **Computation Trace View**: Provides full step-by-step transparency into the agent controller's decisions, tool execution costs, and evidence sufficiency progression.
* **Interactive What-If Sandbox**: Enables planners to adjust port capacity multipliers or hazard durations to instantly inspect alternative network solutions.
* **Human Action Gateway**: Explicit review interface (`Approve`, `Edit`, `Reject`). Every planner decision is recorded in Decision Memory.

---

## 9. Non-Functional, Security & Safety Requirements

* **Untrusted Data Isolation**: All retrieved documents and news articles are treated as untrusted data. Passages are isolated in quoting containers and never directly concatenated into prompt instruction channels.
* **Tool-Isolated Extractor**: The information extraction LLM operates without access to operational tools, preventing prompt injection attacks from executing system actions.
* **Document Trust Tiers**: Vector documents are classified into discrete trust tiers (Tier A: official authorities; Tier B: mainstream trade press; Tier C: social media). Low-trust or expired entries are down-weighted by the grader.
* **Citation-Enforced Release**: The explanation engine cannot release operational guidance to the dashboard unless every claim is verified against a valid evidence ID or computed artifact ID.
* **System Determinism & Auditability**: All random seeds are strictly parameterized. Traces are stored in append-only JSONL files documenting transitions, solver outputs, and token/time costs.
* **Containerization**: The entire platform runs within Docker, guaranteeing one-command reproducibility across environments.

---

## 10. Technical Stack & API Specification

### 10.1 Technology Stack
* **Language & Validation**: Python 3.11, Pydantic v2
* **Graph Engine**: NetworkX, OSMnx
* **Storage Systems**: SQLite (relational events/graph), DuckDB (time-series), FAISS (vector index)
* **Agent Core**: Custom typed finite-state machine, PyTorch (masked MLP policy)
* **Optimization Solvers**: Google OR-Tools, SciPy HiGHS
* **Web & UI Framework**: FastAPI, Uvicorn, React, TypeScript, Cytoscape.js
* **Testing & CI/CD**: PyTest, Hypothesis, Docker, GitHub Actions

### 10.2 REST API Specification

| Endpoint | Method | Operational Function |
| :--- | :--- | :--- |
| `/events` | `POST` | Ingests a new disruption alert; runs Stage A extraction and entity resolution. |
| `/events/{id}` | `GET` | Retrieves structured event details, confidence scores, and lifecycle state. |
| `/events/{id}/plan` | `POST` | Triggers the Stage C agentic loop with a specified cost budget parameter $\lambda$. |
| `/plans/{id}` | `GET` | Returns an optimized routing plan, flow allocations, and L1–L3 verification results. |
| `/traces/{id}` | `GET` | Returns the complete chronological operator execution trace and cost metrics. |
| `/evidence/{id}` | `GET` | Fetches an evidence item with full provenance, trust tier, and supported claims. |
| `/network` | `GET` | Returns active corridor graph topology, node multipliers, and flows. |
| `/registry` | `GET` | Returns the canonical entity registry (IDs, names, aliases, coordinates). |
| `/whatif` | `POST` | Recomputes flow solutions for user-adjusted severities or durations. |
| `/decisions` | `POST` | Records planner feedback (`Approve`, `Edit`, `Reject`) to Decision Memory. |
| `/outcomes` | `POST` | Ingests realized post-event data to trigger Loop L1 graph recalibrations. |

---

## 11. Evaluation Protocol & Target Metrics

### 11.1 Benchmark Test Suites
* **Suite S1 (Single-Event Core)**: Evaluates single-point disruption responses across network configurations and ambiguity levels.
* **Suite S2 (Event Timelines)**: Evaluates multi-day cascading disruptions with updates, escalations, and retractions.
* **Suite S3 (Adversarial Robustness)**: Injects false news, prompt injection payloads, and corrupted vector chunks.
* **Suite S4 (Plan Fault Mutations)**: Injects capacity violations, closed-edge traversals, and cost distortions to validate L2/L3 verifier catch rates.
* **Suite S5 (Live Demonstration Episodes)**: Runs end-to-end demonstrations using live or replayed streaming feeds.
* **Suite S6 (Historical Backtests)**: Replays documented regional events (e.g., Cyclone Michaung) and benchmarks predictions against historical IMF PortWatch AIS volume drops.

### 11.2 Empirical Success Targets

| Area | Baseline Comparison | Empirical Target Metric |
| :--- | :--- | :--- |
| **Adaptive Computation** | Fixed-full operator pipeline | $\ge 40\%$ lower mean compute cost at comparable plan regret |
| **Analytical Depth** | Binary depth classifier | $\text{AUROC} \ge 0.80$, Expected Calibration Error $\text{ECE} \le 0.08$ |
| **Risk-Aware Planning** | Deterministic single-state routing | $\ge 15\%$ reduction in 95th-percentile regret at $\le 5\%$ higher mean cost |
| **System Verification** | Injected constraint/logic faults | $\ge 99\%$ catch rate on injected plan faults; $0\%$ state modification from prompt injection |
| **Retrieval Value** | No-RAG and fixed-RAG pipelines | Lower regret than no-RAG at $\le 1.5\times$ cost; Recall@5 on planted analogues $\ge 0.80$ |
| **Explanation Grounding** | Unchecked generative summaries | $\ge 95\%$ of released explanation assertions supported by verified citations |

---

## 12. Engineering Ownership & 14-Week Roadmap

### 12.1 Engineering Ownership Matrix
* **M1 (Agent Core & RAG Lead)**: Stage C controller, baseline planners, evidence grader, query rewriters, and explainer.
* **M2 (Graph & Optimization Lead)**: Stage B corridor network model, path engine, line-stop calculations, propagation simulators, and OR-Tools solvers.
* **M3 (Data & Integration Backbone Lead)**: Stage A source adapters, PortWatch anomaly detectors, canonical Entity Registry, USKL stores, and FastAPI core.
* **M4 (Frontend & Visualization Lead)**: Stage E Cytoscape.js corridor mapping, evidence view, computation trace panel, and what-if sandbox.
* **M5 (QA, Evaluation & Delivery Lead)**: Verification testing suites, synthetic benchmark generation with planted analogues, CI/CD pipeline, and Docker reproducibility.

### 12.2 Tiered MVP Rollout
* **Tier 1 (Core MVP)**: Unified pipeline over canonical Entity Registry, rule-based controller router, text + graph retrieval, hop-decay propagation, OR-Tools deterministic flow solver, L1–L3 verifier, and baseline dashboard.
* **Tier 2 (Advanced Adaptive)**: Time-series retrieval, dynamic load-redistribution simulator, multi-scenario CVaR optimization, learned masked MLP controller policy, and S6 real-event backtests.
* **Tier 3 (Stretch Capabilities)**: Graph Neural Network (GNN) surrogate propagation model (retained only if outperforming simulation benchmarks), DAgger policy refinement, and RoRo finished-vehicle commodity support.

### 12.3 14-Week Vertical Slice Roadmap

```
W1-W2: Data Readiness (Gate G0) & Walking Skeleton in CI (Gate G1)
  │
W3-W4: Ingestion Adapters, Entity Gazetteer & Tagged Vector Store
  │
W5-W6: Path Risk Engine, Line-Stop KPI, Synthetic Benchmark & Verifiers L1-L3 (Gate G2/G3)
  │
W7-W8: Time-Series Engine, Load Propagation, Scenario Builder & Dashboard v1
  │
W9:    Operator Cost Profiling & Rule/Fixed/LLM Baselines
  │
W10-W11: Oracle Trajectory Labeling & Learned Masked Controller Training (Gate G4)
  │
W12:   Comprehensive Benchmark Execution, Ablations & S6 Event Backtests
  │
W13:   End-to-End Live Integration, Trace Visualizations & S3 Red-Team Audit
  │
W14:   System Code Freeze, One-Command Reproducibility Run & Demo (Gate G5)
```

* **Gate G0 (Week 2)**: Verification of API accessibility, licensing terms, and geographical coverage for all external data sources, or fallback activation.
* **Gate G1 (Week 2)**: Walking skeleton executes end-to-end (Event $\rightarrow$ Graph $\rightarrow$ Router $\rightarrow$ Optimiser $\rightarrow$ Verifier $\rightarrow$ Dashboard stub) with passing CI tests.
* **Gate G2 (Week 6)**: Path impact and line-stop calculations prove reproducible under fixed random seeds; baseline optimization yields zero constraint breaches.
* **Gate G3 (Week 6)**: L1–L3 verifier catches $\ge 99\%$ of injected synthetic faults across mutation test suite S4.
* **Gate G4 (Week 11)**: Learned controller policy emits strictly valid operators under masking; explanation outputs pass automated citation checks.
* **Gate G5 (Week 14)**: Complete evaluation benchmarks and historical backtests execute and regenerate from a single shell command within Docker.

---

## 13. Risk Management & Design Decisions

| Risk Identified | System Impact | Technical Mitigation |
| :--- | :--- | :--- |
| **Public Data Sparsity** | Insufficient port granularity or publishing delays | Gate G0 data verification; fallback to calibrated aggregates; open disclosure of synthetic boundaries |
| **Synthetic-to-Real Gap** | Synthetic evaluations fail to reflect reality | S6 historical event backtests against IMF PortWatch AIS data; benchmark method efficiency rather than forecasting accuracy |
| **Live API Unavailability** | Live demo interruptions from external rate limits | Local caching of historical alerts; manual event entry form; replayable scenario episodes |
| **LLM Hallucinations / Injections** | Graph corruption or ungrounded claims | Tool-isolated extraction agent; untrusted quoting containers; document trust tiers; mandatory L1/L3 verifier checks |
| **Agent Execution Runaway** | Cost inflation or execution deadlocks | Hard limit of 12 steps; per-tool quotas; static action masks; forced `ESCALATE` on budget depletion |
| **Learned Policy Neutrality** | Learned controller does not beat simple heuristics | Treat rule router as an authentic baseline; report parity openly if advanced policy ties threshold rules |