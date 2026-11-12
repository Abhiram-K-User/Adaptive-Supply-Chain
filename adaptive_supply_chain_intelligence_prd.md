# Product Requirements Document (PRD)
## Adaptive Supply Chain Intelligence Platform (Integrated Agentic-RAG Edition)

---

## 1. Document Control & Metadata

* **Product Name**: Adaptive Supply Chain Intelligence Platform
* **Edition**: Integrated Agentic-RAG Edition (v2.0)
* **Date**: 16 October 2026 (Revises v1.0 dated 30 September 2026)
* **Target Industry**: Automotive and automotive components logistics (containerised parts, import/export)
* **Target Geography**: South India port-hinterland corridor (Karnataka, Tamil Nadu, Andhra Pradesh, Kerala)
* **Core Architecture**: One pipeline operating over a Unified State & Knowledge Layer (USKL); agentic RAG controller; deterministic optimisation and layered verification under human-in-the-loop governance
* **Decision Mode**: Decision support with mandatory verification, cited evidence, and human review
* **Team Allocation**: 5 cross-functional engineering leads
* **Authoritative Reference**: *Adaptive Supply Chain Intelligence – Technical Design and Methodology Report v2.0* (39 pages)
* **Scope in One Line**: Containerised auto-component flows between plant clusters (Bengaluru–Hosur, Sriperumbudur–Oragadam, Sri City, Coimbatore) and gateway ports (Chennai, Kamarajar, Kattupalli, Krishnapatnam, Tuticorin, Cochin, New Mangalore), with rail and road links, on a daily planning horizon.

---

## 0. What Changed from v1.0 (PDF Section 0)

| Review Request | What Changed | Relevant Sections |
| :--- | :--- | :--- |
| **1. Complete integration, not independent modules** | The three "modules" are now stages of one pipeline over a single Unified State & Knowledge Layer (USKL) with one canonical entity registry. Every store (graph, events, documents, time-series, decisions) uses the same node/edge IDs. Four closed feedback loops make later runs depend on earlier ones. The software-supply-chain / GitHub-dependency idea has been removed; GitHub appears only as CI tooling. | Sec. 3, 4, 5 |
| **2. Limit scope to one industry and region, based on available data** | Scope fixed to automotive & auto-components logistics in the South India port–hinterland corridor. A dataset matrix lists each public source, what it supplies, and where synthetic data is unavoidable. A Week-2 data-readiness gate (Gate G0) verifies access before design is frozen. | Sec. 2 |
| **3. Computational RAG made agentic** | Retrieval is no longer a single lookup. An agentic RAG core plans, chooses among text, graph, and time-series retrieval *and* computation tools, grades evidence sufficiency, rewrites queries, cites sources, and stops under a cost-aware policy. It is compared against no-RAG, fixed-RAG, and LLM-planner baselines. | Sec. 6 |
| **4. Other improvements** | Real-event backtesting; a plant-level "time-to-line-stop" KPI suited to just-in-time automotive; PortWatch anomaly-triggered events; tiered MVP; retrieval-specific evaluation; retrieval-poisoning defences; calibrated uncertainty; updated roadmap built on vertical slices. | Sec. 10–13 |

---

## 2. Industry & Region Scope

### 2.1 Why Automotive Logistics in South India
* **Just-in-Time Sensitivity**: Automotive plants hold days, not weeks, of inbound components. A port or road disruption translates quickly into a possible line stoppage, which gives the project a concrete, plant-level outcome metric (Time-to-Line-Stop).
* **Dense, Short Corridors with Real Alternatives**: Several plant clusters sit within a few hours of more than one gateway port, with rail links from inland container depots. Rerouting decisions are therefore genuine, not trivial.
* **Recurring, Documented Regional Hazards**: The north-east monsoon and Bay of Bengal cyclones regularly disrupt the Chennai-area coast. This yields a steady stream of events for live demonstration and a historical case library for retrieval.
* **Open Data Availability**: Port-level activity, hazard alerts, news events, road/rail geometry, and trade statistics are public. Plant-level flows are not, and are generated synthetically.

### 2.2 Scope Boundaries

| Dimension | In-Scope | Out-of-Scope |
| :--- | :--- | :--- |
| **Industry** | Automotive and auto-components logistics only | Other industries; pan-India or global network |
| **Region** | Karnataka, Tamil Nadu, Andhra Pradesh, Kerala corridor; out-of-region gateways only as boundary nodes | Full national network; international hinterlands |
| **Commodities** | One commodity class: containerised auto components, inbound and outbound | Multi-commodity optimization; roll-on/roll-off (RoRo) finished vehicles (Tier 3 stretch only) |
| **Modes** | Road, rail and port nodes/edges; daily horizon | Air freight, last-mile delivery, tier-3+ supplier mapping |
| **Disruptions** | Weather/hazard, port congestion or strike, road/rail closure, shipping schedule change, trade-policy change, plant outage | Autonomous execution of logistics actions; replacing human dispatchers |
| **Evaluation** | Synthetic benchmark + real-event backtests + live demonstration | Claiming real-world forecasting accuracy from live news |

### 2.3 Network Graph Dimensions
* **Target Scale**: Directed multigraph $G = (V, E)$ consisting of approximately 100–150 nodes and 300–500 edges.
  * 7–8 gateway maritime ports (Chennai, Kamarajar, Kattupalli, Krishnapatnam, VOC Tuticorin, Cochin, New Mangalore)
  * 5–6 rail terminals / inland container depots (ICD Whitefield, ICD Irugur, etc.)
  * 25–40 plant or supplier nodes grouped by cluster (Sriperumbudur–Oragadam, Bengaluru–Hosur, Bidadi–Harohalli, Sri City, Coimbatore)
  * 15–25 warehouse / container freight station (CFS) nodes
  * ~10 outbound market gateways

### 2.4 Dataset Matrix & Verification

| Source | Provides | Role in System | Status / Fallback |
| :--- | :--- | :--- | :--- |
| **IMF PortWatch** | Daily AIS-derived port calls and trade-volume estimates | Port baseline throughput; ground truth for backtests; anomaly-triggered events | **Real**. Fallback: synthetic port series calibrated to published totals |
| **GDACS** | Alerts for cyclones, floods, earthquakes with location and severity | Live hazard events; hazard-to-port intersection | **Real**. Fallback: cached disaster alerts |
| **GDELT & RSS** | Global news events; local advisories | Unstructured event text for extraction; documents for vector memory | **Real (noisy)**. Fallback: curated regional news archive |
| **Weather / IMD APIs** | Rainfall and wind forecasts; official warnings | Severity priors; time-series retrieval | **Real**. Fallback: manual or scraped IMD bulletins |
| **OpenStreetMap (OSMnx)** | Road and rail geometry; port and terminal locations | Edge topology, distances, transit-time estimates | **Real**. Primary network backbone |
| **Trade Statistics** | Auto-sector trade value by partner; port traffic statistics | Demand weights for outbound lanes; calibration of synthetic flows | **Real (coarse)**. Fallback: published annual aggregates |
| **Plant Operations** | Locations, days-of-cover, flows, edge costs, demand | Line-stop exposure calculations, flow constraints | **Synthetic**. Calibrated against published port container volumes |

> **Honest Data Position**: Topology, locations, hazards, news, and port activity are real. Plant-level operational data is synthetic by necessity. Results on the synthetic benchmark measure the **method**; backtests on real events (Section 11) check that the method behaves sensibly on real signals. Neither is claimed as proof of real-world forecasting accuracy.

---

## 3. Integrated Architecture

### 3.1 From Modules to One System (Stage Coupling & Failure Modes)

| Stage | Consumes (from) | Produces (for) | Breaks if Missing |
| :--- | :--- | :--- | :--- |
| **A. Event Intelligence** | Feeds, analyst input, PortWatch anomalies; graph registry for entity resolution; vector memory for disambiguation and priors | Typed event with graph-resolved targets (to B, C) | Events cannot be grounded to graph IDs |
| **B. Corridor Risk Graph** | Resolved event (A); time-series baselines; retrieved severity/duration priors (C) | Affected paths, exposure, line-stop risk, alternative capacity (to C, optimiser) | No path impact, no features for the controller |
| **C. Agentic RAG Controller**| Event (A); graph features (B); all knowledge stores; cost budget $\lambda$ | Operator sequence, evidence set, scenarios, explanation (to optimiser, verifier, dashboard) | No adaptive depth, no evidence, no explanation |
| **D. Optimise & Verify** | Graph state (B); scenarios (C); event grounding (A) | Verified plan or escalation (to E) | No safe plan release |
| **E. Dashboard & Human Review** | Plan, paths, evidence, trace | Decisions, edits, outcomes (back to memory, graph, controller training) | Loop never closes; system cannot learn |

### 3.2 Unified State & Knowledge Layer (USKL)

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

1. **Corridor Graph Store** (NetworkX, SQLite/JSON): Nodes, edges, capacities, multipliers, plant days-of-cover. Linked by Entity Registry IDs.
2. **Event Store** (SQLite): Typed events, clusters, lifecycle state (`new`, `updated`, `retracted`, `expired`). Linked by target node/edge IDs.
3. **Vector Memory** (FAISS + sentence-transformers): Advisories, incident reports, past event summaries, playbooks; each chunk tagged with graph entity IDs, region, hazard type, and date.
4. **Time-Series Store** (DuckDB / SQLite): Port calls, rainfall, baselines, realised outcomes. Linked by port/node IDs.
5. **Decision & Trace Memory** (SQLite + JSONL): Human approvals/edits/rejections, outcomes, operator traces, plan history. Linked by event, plan, and entity IDs.

### 3.3 Pipeline Logic
1. A live source, a PortWatch anomaly, or an analyst submits an event.
2. Event Intelligence extracts a typed record and resolves it against the entity registry, using retrieval to disambiguate places and set priors.
3. The graph engine applies the event to the graph and computes direct exposure, affected paths, and plant line-stop risk.
4. The agentic controller observes the combined state and chooses the next retrieval or computation operator; each result is written back immutably.
5. The deterministic optimiser produces the candidate plan; the three-layer verifier checks grounding, feasibility, decision sanity, and citation support.
6. The dashboard presents plan, affected paths, evidence, and trace for human approval, edit, or rejection.
7. The decision, and later the realised outcome, are written to memory and to the time-series store.

### 3.4 Closed Feedback Loops
* **Loop L1 (Outcome $\rightarrow$ Graph)**: Realised PortWatch activity after an event updates edge/node multiplier estimates and severity priors.
* **Loop L2 (Decision $\rightarrow$ Memory)**: Planner approvals, edits, and rejections are stored with the event and plan. Retrieved as decision precedents; used in plan-churn checks.
* **Loop L3 (Trace $\rightarrow$ Controller)**: Operator traces with measured costs become oracle-labelled training data for controller retraining.
* **Loop L4 (Event $\rightarrow$ Knowledge)**: Every validated event and its resolution is chunked, tagged, and added to vector memory to expand the analogue incident library.

### 3.5 Integration Contracts and Rules
* Every operator follows `run(state, cfg, rng) -> (new_state, OpResult)`. State is typed (Pydantic v2) and immutable at operator boundaries; randomness only through `rng`; cost is measured, never self-reported.
* Walking skeleton first. An event travels end to end (`event -> graph -> rule router -> optimiser -> verifier -> dashboard stub`) with stubs where needed. Every phase replaces stubs with real components while the end-to-end test stays green.
* Integration test in CI: a scripted event must produce a verified plan with a complete trace on every merge.
* Mocks are temporary scaffolding; none may remain at the final freeze.

---

## 4. Stage A: Live Event Intelligence (Corridor-Specific)

### 4.1 Event Sources and Processing

| Step | Implementation | Integration Point |
| :--- | :--- | :--- |
| **Ingest** | Scheduled polling of GDACS, GDELT and RSS; analyst event form; PortWatch anomaly detector that raises an event when a port's daily calls fall well below its baseline | Time-series store feeds the detector; events are stored in the event store |
| **Classify** | Rules or a lightweight LLM classifier for corridor relevance | Uses region/hazard tags from the registry |
| **Extract** | Rules first; structured-output LLM as fallback. The extraction LLM has no tools and sees only the article text | Output validated against Pydantic schema |
| **Resolve** | Fuzzy matching and embeddings against the graph gazetteer (node names, aliases, geography); retrieval of similar past resolutions | Targets expressed as registry IDs with probabilities |
| **Validate** | Schema and grounding checks; source corroboration count | L1 verification record |
| **Store** | Deduplication, updates, retractions, expiry; cluster into a belief state | Event store; chunk and tag into vector memory (Loop L4) |

### 4.2 Regional Event Taxonomy
1. `HAZARD_PORT`: Cyclone landfall or red rain alert near Chennai–Ennore coast (port capacity multiplier, delay).
2. `HAZARD_ROAD`: Flooded underpass or highway closure on a plant–port road (edge closure or multiplier, added transit time).
3. `PORT_CONGESTION_STRIKE`: Berth congestion, labour action, customs system outage (port handling capacity, dwell time).
4. `RAIL_DISRUPTION`: Track blockage on an ICD–port rail link (rail edge multiplier; shift of load to road).
5. `SHIPPING_SCHEDULE`: Blank sailings or route diversion on a trade lane (outbound gateway capacity or delay).
6. `TRADE_POLICY`: Tariff or regulatory change affecting an export market (demand weight on outbound lanes).
7. `PLANT_OUTAGE`: Component supplier breakdown or assembly plant stoppage (node capacity, upstream flow).

---

## 5. Stage B: Corridor Risk Graph & Path-Impact Prediction

### 5.1 Graph Model
Directed multigraph $G = (V, E)$ storing capacity, utilisation, cost, transit time, and current multipliers; plant nodes also store inventory days-of-cover.

### 5.2 Affected-Path Algorithm
1. Resolve event targets to registry IDs (from Stage A).
2. Apply the multiplier or delay and build the affected $k$-hop subgraph.
3. Enumerate feasible plant-to-gateway paths traversing affected elements.
4. Compute path exposure, alternative capacity, bottleneck concentration, and criticality.
5. Compute plant-level line-stop risk.
6. Run propagation if the controller selects it; rank paths by risk; write features to the shared state.

### 5.3 Risk Features and Line-Stop Metric
* **Exposure**: Share of baseline flow behind the affected element:
  $$\text{Exposure}(e) = \frac{\text{Baseline Flow across element } e}{\text{Total Corridor Flow}}$$
* **Criticality**: Normalised betweenness $\times$ utilisation $\times$ demand dependency:
  $$\text{Criticality}(e) = \text{Betweenness}(e) \times \text{Utilisation}(e) \times \text{Demand Dependency}(e)$$
* **PathRisk**: Ranking score:
  $$\text{PathRisk}(p) = \text{Exposure} \times \text{Criticality} \times \text{Severity} \times \text{UncertaintyFactor} \times \text{Concentration}$$
* **Plant-Level Line-Stop Metric**:
  $$\text{Time-to-Line-Stop}(\text{Plant } v) = \text{Inventory Days-of-Cover}(v) - \text{Expected Inbound Delay}(v)$$
  Calculates the probability that inbound transit delays exceed available days-of-cover across scenarios.

### 5.4 Propagation
* **Tier 1 (Hop-Decay)**: Deterministic BFS hop-decay cascade attenuating adjacent corridor capacities ($m \times \gamma^{\text{hop}}$).
* **Tier 2 (Dynamic Load Redistribution)**: Simulates diversion effects (port capacity down $\rightarrow$ diverted load up $\rightarrow$ road congestion up $\rightarrow$ inventory down $\rightarrow$ delay up) using nonlinear BPR volume-delay functions.
* **Tier 3 (GNN Surrogate)**: Stretch capability, retained only if outperforming simulation benchmarks.

---

## 6. Stage C: Agentic RAG Computational Core

### 6.1 Concept & Design Stance
* **Agentic & Computational**: A controller observes the state, decides what to do next, calls a tool, grades the result, and decides again. Tools include text retrieval, graph queries, time-series analysis, and numerical solvers.
* **Design Stance**: One orchestrator with typed tools, not a swarm of autonomous agents. Keeps state, cost accounting, and safety masks tractable.
* **Role Separation**: The LLM interprets text, rewrites queries, grades evidence, and writes explanations. It never decides feasibility or optimises; deterministic code does.

### 6.2 Retrieval Tools (Four Sources, One Registry)

| Tool | Store | Query Form | Returns | Used For |
| :--- | :--- | :--- | :--- | :--- |
| `RETRIEVE_TEXT` | Vector memory | Semantic query + filters (entity IDs, hazard type, date range) | Ranked passages with IDs, dates, sources | Analogue incidents, advisories, playbook steps |
| `RETRIEVE_GRAPH` | Corridor graph | $k$-hop subgraph around entity IDs; dependency facts | Subgraph + natural-language facts with provenance | Dependency context for explanation and priors |
| `RETRIEVE_TS` | Time-series store | Parameterised query (port, window, hazard analogue) | Series statistics: baseline, drop, recovery time | Severity/duration priors; outcome checks |
| `RETRIEVE_DECISIONS`| Decision & trace memory| Similar event + plan lookup | Past plans, edits, outcomes | Precedent and plan-churn context |

### 6.3 Agent Roles

| Role | Implemented By | Responsibility |
| :--- | :--- | :--- |
| **Controller (planner)** | Learned masked policy (MLP); rule router and LLM planner as baselines | Choose next operator from valid set; decide `STOP` or `ESCALATE` |
| **Query rewriter** | LLM, constrained to structured output | Reformulate failed query using entity IDs and hazard terms; limited to 2 rewrites |
| **Retrievers** | Deterministic code over USKL stores | Execute queries, return IDs and provenance |
| **Grader** | Small LLM or cross-encoder + rules | Score relevance of each item and sufficiency of evidence set ($0.0$–$1.0$); triggers rewrite |
| **Computation tools** | Deterministic code (graph, simulator, scenarios, OR-Tools) | Produce numerical artefacts with IDs |
| **Verifier** | Deterministic checks (+ citation checker) | `PASS`, `REPAIR`, or `ESCALATE` |
| **Explainer** | LLM over computed artefacts and evidence only | Write rationale; every claim must cite an evidence ID or computed artefact ID |

### 6.4 Action Space & Masking Rules

| Operator | Cost Class | Mask Rule (Valid When) |
| :--- | :--- | :--- |
| `GRAPH_ANALYZE` | Low | Event resolved; always valid first after perception |
| `RETRIEVE_TEXT` / `_GRAPH` / `_TS` / `_DECISIONS` | Low–medium | Event resolved; per-tool call limit not exceeded |
| `REWRITE_QUERY` | Low | Previous retrieval graded insufficient; rewrite count $< 2$ |
| `GRADE` | Low | New evidence exists since last grade |
| `PROPAGATE` | Medium | Graph analysis done |
| `SCENARIOS` | Medium | Graph analysis done; uncertainty or impact above gate |
| `OPTIMIZE` | High | Required state available (graph analysis; scenarios if requested) |
| `VERIFY` | Low | A plan exists |
| `STOP` | None | Only after `VERIFY == PASS` |
| `ESCALATE` | None | Always valid; forced by safety rules or budget exhaustion |

### 6.5 Control Loop & Policy Objective
The controller observes a feature vector built from the shared state:
$$J(\pi) = \mathbb{E} \left[ \text{Regret}(\text{Plan}) + \lambda \sum_{t=1}^T \text{Cost}(\text{Operator}_t) \right]$$
Cost is measured wall-clock time plus LLM tokens per operator, profiled once and logged per run.

### 6.6 How Retrieval is Woven into the Other Stages (PDF Table 6.6)

| Consumer | What Retrieval Supplies | Effect |
| :--- | :--- | :--- |
| **Stage A — Entity Resolution** | Similar past place-name resolutions; gazetteer aliases | Fewer mis-grounded targets |
| **Stage A/B — Severity & Duration** | Distribution of impact and recovery times from analogue incidents and port-call series | Informed priors when news text gives no duration |
| **Scenario Generation** | Analogue outcomes $\rightarrow$ scenario set and weights | Evidence-based scenario probabilities, not arbitrary ones |
| **Explanation** | Cited passages and artefacts | Auditable rationale |
| **Verification (L3)** | Citation-support check: each cited ID must exist and support claim | Blocks unsupported statements |

### 6.7 Learning Strategy
1. **Baselines First**: Always-full pipeline; rule router (thresholds on confidence/exposure); fixed RAG; LLM planner.
2. **Planted-Analogue Benchmark**: Synthetic generator creates historical case library where past events carry known outcomes.
3. **Oracle Labels**: Enumerate valid operator sequences on training instances, compute realized regret and measured cost, label best sequence per $\lambda$.
4. **Imitation Learning**: Train a small masked MLP on oracle labels; add DAgger only if time permits.
5. **Honest Reporting**: Rule router is a real baseline. If learned controller ties it, report as is.

### 6.8 Safety for Agentic RAG
* **Retrieved Text is Untrusted Data**: Wrapped as quoted evidence, never concatenated into prompt instructions; extraction LLM has no tools.
* **Tool Allow-List and Hard Masks**: Step limit (12), per-tool call limits, budget cap. Hitting limits forces `ESCALATE`.
* **Retrieval Poisoning and Staleness**: Trust tiers (Tier A/B/C), dates, expired items down-weighted; conflicting sources raise uncertainty.
* **Citation-Required Output**: Explainer cannot release claims without supporting IDs; L3 verification rejects unsupported claims.
* **Confidence Gates**: High-impact and low-confidence events trigger full-analysis fallback or human escalation.

---

## 7. Optimisation & Layered Verification

### 7.1 Multi-Commodity Minimum-Cost Flow Formulation
$$\min \sum_{(i,j) \in E} \sum_k c_{ij}^k x_{ij}^k + \sum_{v \in \text{Plants}} P_{\text{line-stop}}(v) \cdot \max(0, \text{Delay}_v - \text{Cover}_v) + \sum_{d \in \text{Demand}} P_{\text{unmet}} \cdot u_d$$
* **Solvers**: Google OR-Tools (primary) and SciPy HiGHS (dual-solver cross-check).
* **Risk Modes**: Deterministic, Expected-Cost, and CVaR (tail-risk protection).

### 7.2 Three-Layer Verification Protocol

| Layer | Checks | Action on Failure |
| :--- | :--- | :--- |
| **L1 Input** | Schema, graph grounding, source corroboration, entity validity, evidence provenance | Reject / repair / escalate |
| **L2 Plan** | Capacity, flow conservation, closed edges, objective recomputation by a second solver | Repair or escalate |
| **L3 Decision** | Unmet demand, line-stop risk threshold, cost sanity, plan churn, confidence gate, citation support of explanation | Repair or human confirmation |

---

## 8. End-to-End Demonstration Scenario (PDF Section 8)

**Illustrative Scenario**: North-east monsoon red-level cyclone/heavy-rain alert over Chennai–Ennore coast. Kamarajar and Kattupalli operate at 40% capacity for 3 days; road flooding risk on plant–port links.

| Step | Operator | Observation Written to State (Illustrative) | Cost Class |
| :---: | :--- | :--- | :---: |
| **0** | **Perception (always)** | GDACS alert + 2 news items $\rightarrow$ `HAZARD_PORT` at Kamarajar and Kattupalli, multiplier 0.40, 3 days, confidence 0.78; targets resolved to registry IDs | Low |
| **1** | **`GRAPH_ANALYZE`** | 14 plant-to-gateway paths affected; ~38% of outbound corridor flow behind the two ports; Oragadam cluster time-to-line-stop $\approx 2.1$ days | Low |
| **2** | **`RETRIEVE_TEXT`** | Three analogue cyclone-closure reports retrieved; duration prior 2–5 days; evidence sufficiency 0.55 (below 0.70 gate) | Medium |
| **3** | **`REWRITE_QUERY` $\rightarrow$ `RETRIEVE_TS`** | Query refined with port IDs; port-call series for two past analogues show a sharp drop and several-day recovery | Medium |
| **4** | **`GRADE`** | Sufficiency $0.82 \ge 0.70 \rightarrow$ proceed | Low |
| **5** | **`PROPAGATE`** | Diverted load raises Chennai Port utilisation; Krishnapatnam spare capacity can absorb a large share | Medium |
| **6** | **`SCENARIOS`** | Three weighted scenarios (moderate, severe, full closure) with analogue-informed weights | Medium |
| **7** | **`OPTIMIZE`** | CVaR plan: pre-reserve Krishnapatnam and Chennai slots; shift selected flows to rail from Bengaluru ICD | High |
| **8** | **`VERIFY`** | L1, L2, L3 PASS; all explanation claims cite evidence or artefact IDs | Low |
| **9** | **`EXPLAIN` $\rightarrow$ `STOP`**| Plan, evidence, and trace released for human approval | Low |

* **Contrast Case**: A minor, high-confidence, low-exposure event (e.g., short delay at rarely used terminal) lets the controller skip retrieval, scenarios, and propagation and go straight from graph analysis to a deterministic plan, saving compute.
* **After the Event**: Realised PortWatch data for affected ports is ingested (Loop L1), planner decision is stored (Loop L2), trace becomes training data (Loop L3), and event summary joins vector memory (Loop L4).

---

## 9. Dashboard Views & Human Review

| View | Information Displayed |
| :--- | :--- |
| **Event Feed** | Events, sources, confidence, lifecycle, PortWatch anomaly flags |
| **Corridor Map** | Nodes/edges, affected paths, multipliers, flow (edge width), uncertainty (ring/opacity) |
| **Risk Panel** | Ranked paths, exposure, bottlenecks, plant time-to-line-stop |
| **Evidence Panel** | Retrieved passages and series with source, date, trust tier; supported claims |
| **Scenario Panel** | Scenario weights and plan cost by scenario; tail risk |
| **Plan View** | Recommended reservations and routes; diff against active plan |
| **Computation Trace** | Operator sequence, cost, why deeper analysis was chosen (retrieval and rewrites) |
| **Verification Panel** | Each check, value, threshold, verdict |
| **What-If Sandbox** | Change severity or duration, recompute fast path |
| **Human Action** | Approve / Edit / Reject, stored to decision memory |

---

## 10. Additional Improvements over v1.0 (PDF Section 10)

| Improvement | Rationale | Tier |
| :--- | :--- | :---: |
| **Canonical Entity Registry across all stores** | Core integration mechanism; removes ID mismatches | Tier 1 |
| **Plant line-stop risk / Time-to-Line-Stop KPI** | Domain-specific outcome for JIT automotive | Tier 1 |
| **PortWatch anomaly-triggered events** | Lets time-series data originate events, not only text feeds | Tier 1–2 |
| **Real-event backtesting** | Replays documented regional events against PortWatch series | Tier 2 |
| **Planted-analogue synthetic benchmark** | Makes benefit of retrieval measurable rather than assumed | Tier 2 |
| **Evidence sufficiency gate & query rewriting** | Prevents over-retrieval and acting on weak evidence | Tier 1–2 |
| **Calibrated uncertainty** | Confidence calibration (isotonic) and conformal intervals | Tier 2 |
| **Retrieval security (poisoning, staleness, injection)** | Trust tiers, quarantine of retrieved text, red-team Suite S3 | Tier 1 |
| **Cost-aware LLM usage** | Response caches, small model for grading, token cost in objective | Tier 1–2 |
| **Tiered MVP** | Tier 1: Core pipeline; Tier 2: Time-series, CVaR, learned controller; Tier 3: GNN, DAgger | — |
| **One-command reproducibility** | Fixed seeds, JSONL traces, Docker image, single script | Tier 1 |

---

## 11. Evaluation Plan & Systematic Ablation Studies (PDF Section 11)

### 11.1 The 9 Systematic Ablation Questions

| Evaluation Question | Comparison | Primary Metric |
| :--- | :--- | :--- |
| **1. Does graph analysis improve impact identification?** | No graph vs. $k$-hop/exposure graph | Affected-path recall; exposure error |
| **2. Does retrieval help?** | No-RAG vs. fixed-RAG vs. agentic-RAG | Regret at equal cost; cost at equal regret |
| **3. Is the retrieval itself good?** | Text-only vs. graph-aware vs. graph + time-series | Recall@$k$ on planted analogues; context precision |
| **4. Are explanations grounded?** | With vs. without citation check | Claim-citation support rate; unsupported-claim rate |
| **5. Is evidence-sufficiency gate calibrated?** | Gate vs. fixed number of retrievals | Calibration of sufficiency vs. correct analogue; steps |
| **6. Does adaptive control save compute?** | Always-full vs. rule router vs. LLM vs. learned controller | Regret vs. cost frontier; AUROC for depth; ECE |
| **7. Does propagation add value?** | Hop-decay vs. simulator (vs. GNN if built) | Recall@10, error, runtime |
| **8. Does scenario planning help?** | Single-state vs. scenario-aware | Tail regret / CVaR; unmet demand; line-stop events |
| **9. Does it work on real events?** | Backtest on documented regional events | Agreement with PortWatch series; lead time; rank correlation |

### 11.2 Benchmark Suites
* **Suite S1 (Single-Event Core)**: Across network sizes and ambiguity tiers.
* **Suite S2 (Timelines)**: Multi-day compound disruptions with updates, retractions, and related reports.
* **Suite S3 (Adversarial Robustness)**: False/conflicting reports, prompt injection in articles and in retrieved docs, poisoned/stale chunks.
* **Suite S4 (Plan Fault Mutations)**: Injected constraint and objective faults.
* **Suite S5 (Live Episodes)**: Short live-feed streaming episodes for qualitative demonstration.
* **Suite S6 (Historical Backtests)**: Real-event backtests against PortWatch series; networks split by topology.

### 11.3 Empirical Targets

| Area | Target / Success Rule |
| :--- | :--- |
| **Adaptive Computation** | $\ge 40\%$ lower mean cost at comparable regret versus fixed-full routing |
| **Depth Prediction** | $\text{AUROC} \ge 0.80$; $\text{ECE} \le 0.08$ |
| **Propagation** | Recall@$10 \ge 10$ points above hop-decay; $\ge 10\times$ faster than simulator (if GNN built) |
| **Risk-Aware Planning** | $\ge 15\%$ lower 95th-percentile regret at $\le 5\%$ higher mean cost |
| **Verification** | $\ge 99\%$ injected-fault catch rate; $0\%$ state change from injected instructions |
| **Retrieval Value** | Agentic RAG achieves lower regret than no-RAG at $\le 1.5\times$ cost; Recall@$5 \ge 0.80$ |
| **Grounding** | $\ge 95\%$ of released explanation claims supported by cited evidence |
| **Demonstration** | Live event $\rightarrow$ graph update $\rightarrow$ affected paths $\rightarrow$ agentic trace with retrieval $\rightarrow$ verified plan, end to end |

---

## 12. Technical Stack & API Specification

### 12.1 REST API Surface

| Endpoint | Purpose |
| :--- | :--- |
| `POST /events` | Submit an event; return event ID and extraction record |
| `GET /events/{id}` | Event, cluster, confidence, lifecycle |
| `POST /events/{id}/plan?lambda=` | Run the agentic controller; return plan, verdict and trace ID |
| `GET /plans/{id}` | Reservations, scenario flows, costs, verification report |
| `GET /traces/{id}` | Operator sequence, cost, timing, state features, retrieved evidence IDs |
| `GET /evidence/{id}` | Retrieved item with source, date, trust tier and claims supported |
| `GET /network` | Current graph, multipliers, predicted impact and uncertainty |
| `GET /registry` | Canonical entity registry (IDs, names, aliases, geography) |
| `POST /whatif` | Change severity/multiplier and recompute a fast path |
| `POST /decisions` | Store human approve / edit / reject |
| `POST /outcomes` | Ingest realised outcomes (e.g. PortWatch series) to recalibrate graph (Loop L1) |

---

## 13. Team Distribution, Roadmap & Development Gates

### 13.1 Engineering Ownership Matrix (Seams of the Integrated System)

| Member | Owns | Key Responsibilities | Primary Stack |
| :--- | :--- | :--- | :--- |
| **M1 — Agent Core & RAG Lead** | Stage C | Controller, baselines, grader, query rewriter, retrieval tools, explainer, oracle labels, LLM interface | Python, PyTorch, LLM API, FAISS |
| **M2 — Graph & Optimisation Lead** | Stage B + Optimiser | Corridor graph, path engine, line-stop risk, propagation, scenarios, OR-Tools | NetworkX, OSMnx, OR-Tools, SciPy |
| **M3 — Data & Integration Backbone** | Stage A + USKL + API | Source adapters, PortWatch detector, entity registry, stores, ingestion of tagged documents, FastAPI | FastAPI, Pydantic, SQLite/DuckDB |
| **M4 — Frontend & Visualisation** | Stage E | Corridor map, evidence panel, trace view, scenario and plan views, what-if | React, Cytoscape.js, TypeScript |
| **M5 — QA, Evaluation & Delivery** | Cross-cutting | Verifier tests, synthetic generator with planted analogues, backtest harness, metrics, CI/CD, reproducibility | PyTest, Hypothesis, Docker, GitHub Actions |

* **Joint Seams Ownership**: M1 + M2 jointly own the controller–graph feature boundary; M2 + M3 own graph and event contracts; M1 + M3 own vector-memory schema and tagging.
* **Weekly Integration Build**: On a fixed day, the end-to-end scripted event must pass before new features merge.

### 13.2 Fourteen-Week Vertical Slice Roadmap

| Weeks | Milestone | Owners |
| :---: | :--- | :--- |
| **1–2** | Data-readiness check (Gate G0); entity registry; corridor graph v0; walking skeleton with stubs and CI integration test | M2, M3, M5 |
| **3–4** | Live adapters (GDACS, GDELT/RSS, PortWatch anomaly detector); extraction and entity resolution; vector memory ingestion with graph tags; curated regional case library | M1, M3 |
| **5–6** | Path-impact engine and line-stop risk; text + graph RAG with grader; synthetic generator with planted analogues; verifier L1–L3 | M1, M2, M5 |
| **7–8** | Time-series retrieval; hop-decay and simulator propagation; scenarios; backtest harness; dashboard v1 with evidence panel | M2, M4, M5 |
| **9** | Operator wrappers, cost profiling, agent executor, rule/LLM/fixed-RAG baselines | M1, M2, M3 |
| **10–11**| Oracle labels, imitation policy, safety masks; GNN only if time remains | M1, M5 |
| **12** | Full benchmark, ablations, backtests, statistical evaluation | M5, all |
| **13** | Live end-to-end integration, trace/evidence visualisation, red-team suite S3 | M3, M4, M5 |
| **14** | Freeze, one-command reproducibility run, report and demo | All |

### 13.3 Development Gates

| Gate | Target | Pass Condition |
| :---: | :--- | :--- |
| **G0** | Week 2 | Each dataset in Section 2.4 verified for access, licence, and coverage, or its fallback chosen |
| **G1** | Week 2 | Walking skeleton runs event $\rightarrow$ verified plan; CI integration test green |
| **G2** | Week 6 | Affected-path and line-stop outputs reproducible for fixed seeds; baseline optimisation has zero unintended violations |
| **G3** | Week 6 | Verifier catches injected faults in the mutation suite ($\ge 99\%$) |
| **G4** | Week 11| Controller emits only valid actions; trace includes retrieved evidence IDs; explanations pass citation check |
| **G5** | Week 14| Held-out evaluation and backtests frozen; all results regenerate from one command |

---

## 14. Risks & Design Decisions

| Risk Identified | System Impact | Technical Mitigation |
| :--- | :--- | :--- |
| **Public data coarser or less available than assumed** | Weak calibration; thin backtests | Gate G0; documented fallbacks; synthetic generator calibrated to aggregates; state limits openly |
| **Synthetic-to-real gap** | Results do not transfer | Backtests on real events; claim method-level results only |
| **Live API instability / rate limits** | Demo interruption | Cached events; analyst-input fallback; replayable episodes |
| **LLM hallucination, prompt injection, poisoned documents** | Wrong graph update or unsupported claim | No-tools extractor; untrusted-text handling; trust tiers; L1 and L3 verification; S3 suite |
| **Agent loops or runaway cost** | Slow or expensive runs | Step, tool and budget limits; hard masks; forced `ESCALATE` |
| **Adaptive policy ties rule router** | Weaker novelty claim | Treat router as real baseline; report ties |
| **GNN underperforms heuristic** | Weak research result | GNN is Tier 3; heuristic stays default |
| **Scope creep** | Schedule failure | Fixed industry and region; tiered MVP; one commodity |
| **Integration delays** | Team blocking | Walking skeleton Week 2; CI integration test; typed contracts; weekly integration build |

---

## Appendix A — Unified State Schema Excerpt (JSON)

```json
{
  "event": {
    "id": "ev_0188",
    "type": "HAZARD_PORT",
    "targets": [{"id": "PORT_KAMARAJAR", "p": 0.92}],
    "capacity_multiplier": 0.40,
    "duration_days": 3,
    "confidence": 0.78
  },
  "graph": {
    "version": "g_2026-10-16",
    "affected_paths": 14,
    "flow_exposure": 0.38,
    "plant_line_stop": {
      "PLANT_ORAGADAM": {"time_to_line_stop_days": 2.1}
    }
  },
  "evidence": [
    {
      "id": "doc_0412",
      "source": "rss",
      "date": "2023-12-05",
      "trust": "B",
      "entities": ["PORT_CHENNAI"]
    }
  ],
  "sufficiency": 0.82,
  "results": {
    "propagation": "art_p07",
    "scenarios": "art_s03",
    "plan": "plan_0091"
  },
  "budget": {
    "lambda": 0.2,
    "steps": 8,
    "cost_spent": 6.4,
    "step_limit": 12
  },
  "trace": [
    "GRAPH_ANALYZE",
    "RETRIEVE_TEXT",
    "REWRITE_QUERY",
    "RETRIEVE_TS",
    "GRADE",
    "PROPAGATE",
    "SCENARIOS",
    "OPTIMIZE",
    "VERIFY",
    "STOP"
  ]
}
```

---

## Appendix B — Agent Loop Pseudocode

```python
state = perceive(event)                        # always runs; resolves to registry IDs
while not state.done:
    mask = valid_operators(state)              # hard safety + precondition masks
    action = policy(features(state), lam, mask)
    if action == STOP:
        break                                  # only valid after VERIFY == PASS
    if action == ESCALATE:
        state = escalate(state)
        break
    state, result = TOOLS[action].run(state, cfg, rng)  # retrieve OR compute; cost measured
    if action in RETRIEVE_TOOLS:
        state = grade(state)                   # relevance per item + evidence sufficiency
        if state.sufficiency < GATE and state.rewrites < 2:
            state.force = REWRITE_QUERY
    if state.steps >= STEP_LIMIT or state.cost > BUDGET:
        state = escalate(state)
        break

release(state) if state.verify == PASS else hand_to_human(state)
```

---

## Appendix C — Data Sources to Verify in Week 1–2 (Gate G0)

| Source | Address / URL | Verification Check |
| :--- | :--- | :--- |
| **IMF PortWatch** | `portwatch.imf.org` (also on `data.humdata.org/organization/portwatch`) | Indian port coverage, API access, update lag |
| **GDACS** | `www.gdacs.org` | Feed format, regional alert history |
| **GDELT** | `www.gdeltproject.org` | Query limits, India/logistics filters |
| **OpenStreetMap** | `www.openstreetmap.org` (OSMnx for extraction) | Road/rail completeness; licence and attribution |
| **UN Comtrade** | `comtradeplus.un.org` | Free-tier limits; HS codes for auto sector |
| **India Open Data**| `data.gov.in`; Ministry of Ports, Shipping & Waterways | Port traffic granularity and recency |
| **Weather** | `open-meteo.com`; `mausam.imd.gov.in` | Terms of use; programmatic access |
