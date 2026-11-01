# Adaptive Supply Chain Intelligence Platform (ASCI)
## Integrated Agentic-RAG Edition v2.0 · South India Automotive Corridor

[![CI Pipeline](https://github.com/adaptive-logistics/asci-core/actions/workflows/ci.yml/badge.svg)](https://github.com/adaptive-logistics/asci-core/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2.12-green.svg)](https://docs.pydantic.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![License: Proprietary / Industrial](https://img.shields.io/badge/license-Industrial%20MVP-orange.svg)]()

The **Adaptive Supply Chain Intelligence Platform (ASCI)** converts multimodal disruption signals (cyclones, port strikes, highway flooding, customs bottlenecks) into verified, evidence-cited response plans for Just-In-Time (JIT) automotive supply chains across South India.

---

## 1. Geographic & Industrial Corridor Focus

The system models the **South India Port-Hinterland Automotive Corridor** across Tamil Nadu, Karnataka, Andhra Pradesh, and Kerala:

* **Gateway Maritime Ports**:
  * `PORT_CHENNAI` (Chennai Port Authority)
  * `PORT_KAMARAJAR` (Ennore / Kamarajar Port)
  * `PORT_KATTUPALLI` (Adani Kattupalli Port)
  * `PORT_KRISHNAPATNAM` (Adani Krishnapatnam Port)
  * `PORT_VOC` (V.O. Chidambaranar Port, Tuticorin)
  * `PORT_COCHIN` (Vallarpadam ICTT)
  * `PORT_NEW_MANGALORE` (New Mangalore Port)

* **Key Assembly Clusters & Tier-1 Hubs**:
  * `PLANT_ORAGADAM` (Renault-Nissan, Daimler India Commercial Vehicles)
  * `PLANT_SRIPERUMBUDUR` (Hyundai Motor India, Tier-1 cluster)
  * `PLANT_HOSUR` (Ashok Leyland, TVS Motor Company)
  * `PLANT_BIDADI` (Toyota Kirloskar Motor)
  * `PLANT_SRICITY` (Isuzu Motors, Kobelco, Tier-1 cluster)
  * `PLANT_COIMBATORE` (Precision components and motor cluster)

* **Inland Container Depots (ICD) & Rail Freight Hubs**:
  * `ICD_WHITEFIELD` (CONCOR Whitefield, Bengaluru)
  * `ICD_TONDIARPET` (CONCOR Tondiarpet, Chennai)
  * `ICD_IRUGUR` (CONCOR Irugur, Coimbatore)

---

## 2. Core Architectural Directives

### 2.1 Unified State & Knowledge Layer (USKL)
All components read from and write to a single **Unified State & Knowledge Layer** bound by the **Canonical Entity Registry**. An entity identifier (e.g., `PORT_KAMARAJAR`, `PLANT_ORAGADAM`) shares the exact same immutable string across:
1. **Corridor Graph Store** (`networkx.MultiDiGraph`)
2. **Event Store** (`SQLiteEventStore`)
3. **Vector Memory** (`SemanticVectorStore`)
4. **Time-Series Store** (`TimeSeriesStore`)
5. **Decision & Trace Store** (`DecisionTraceStore`)

### 2.2 Immutable State & Operator Boundary
Every pipeline operator follows the deterministic contract:
```python
def run(
    self,
    state: PipelineState,
    cfg: PipelineConfig,
    rng: random.Random
) -> tuple[PipelineState, OperatorResult]:
    ...
```
`PipelineState` uses Pydantic v2 `ConfigDict(frozen=True)`. Mutations occur via copy-on-write `state.transition(updates, trace_item)` which automatically increments step counters, accumulates compute costs, and appends chronological execution traces.

### 2.3 Gate G1 "Walking Skeleton" Pipeline
The end-to-end executable vertical slice coordinates five stages:
```
  [Disruption Signal]
           │
           ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage A: Live Event Intelligence & Entity Resolution    │
  └──────────────────────────┬──────────────────────────────┘
                             │ Typed DisruptionEvent (Canonical IDs)
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage B: Corridor Risk Graph & Path Impact Engine       │
  └──────────────────────────┬──────────────────────────────┘
                             │ Path Exposure & Time-to-Line-Stop KPIs
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage C: Agentic RAG Controller & Computation Core      │
  │          (Rule Router Baseline + Scenarios Parameter)   │
  └──────────────────────────┬──────────────────────────────┘
                             │ Evidence Set & Discrete Scenarios
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage D: Deterministic Optimization & Layered Verifier  │
  │          (Rerouting Allocations + L1/L2/L3 Gateways)    │
  └──────────────────────────┬──────────────────────────────┘
                             │ Verified MitigationPlan
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Stage E: Operational Dashboard State-to-UI Serializer   │
  └─────────────────────────────────────────────────────────┘
```

### 2.4 Three-Layer Verification Protocol
* **Layer 1 (L1) Ingestion & Grounding**: Schema compliance, Canonical Entity ID verification, source corroboration checks.
* **Layer 2 (L2) Network Solvency**: Flow conservation, edge capacity multipliers ($x_{ij} \le \text{Cap}_{ij} \cdot \text{Mult}_{ij}$), closed-edge zero flow.
* **Layer 3 (L3) Decision Sanity & Grounding**: Plant line-stop threshold safety, unmet assembly demand bounds, citation grounding against retrieved evidence.

---

## 3. Directory Layout

```text
asci-core/
├── .github/
│   └── workflows/
│       └── ci.yml                     # GitHub Actions CI workflow (Python 3.11)
├── data/
│   └── seeds/
│       ├── corridor_registry.json     # Canonical Entity Registry seed definitions
│       └── corridor_graph_v0.json     # Corridor Multigraph node-link seed
├── src/
│   └── asci/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── registry.py            # Canonical Entity Registry lookup & gazetteer
│       │   ├── state.py               # Immutable Pydantic v2 PipelineState schema
│       │   └── contracts.py           # Operator protocol & OpResult structures
│       ├── uskl/
│       │   ├── __init__.py
│       │   ├── graph_store.py         # NetworkX corridor multigraph store
│       │   ├── event_store.py         # SQLite event lifecycle manager
│       │   ├── vector_store.py        # Semantic vector memory stub & playbooks
│       │   ├── timeseries_store.py    # DuckDB/SQLite baseline & recovery curves
│       │   └── decision_store.py      # JSONL/SQLite trace & human decision store
│       ├── stages/
│       │   ├── __init__.py            # WalkingSkeletonPipeline orchestrator
│       │   ├── stage_a_events.py      # Ingestion, classification, gazetteer resolution
│       │   ├── stage_b_graph.py       # k-hop subgraph, path exposure, line-stop KPI
│       │   ├── stage_c_controller.py  # Rule-router baseline & tool executor
│       │   ├── stage_d_optimiser.py   # Flow solver stub & L1-L3 verification
│       │   └── stage_e_dashboard.py   # State-to-UI Cytoscape serializer
│       ├── api/
│       │   ├── __init__.py
│       │   └── main.py                # FastAPI REST endpoints
│       └── utils/
│           ├── __init__.py
│           └── logging.py             # Structured logger
├── tests/
│   ├── conftest.py                    # PyTest fixtures and USKL setup
│   ├── unit/
│   │   ├── test_registry.py           # Unit tests for registry & gazetteer
│   │   └── test_state.py              # Unit tests for immutability & copy-on-write
│   └── integration/
│       └── test_walking_skeleton.py   # CI Gate G1 integration test
├── Dockerfile                         # Production container image
├── pyproject.toml                     # Modern package build configuration
├── requirements.txt                   # Pinned core and dev dependencies
└── README.md
```

---

## 4. Quickstart Guide

### 4.1 Environment Setup
```bash
cd asci-core
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 4.2 Running the Test Suite (Gate G1 Verification)
Run all unit and integration tests:
```bash
pytest tests/ -v
```
All tests execute deterministically in `< 0.2s`.

### 4.3 Running the FastAPI Service
Launch the Uvicorn server:
```bash
uvicorn asci.api.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive OpenAPI documentation will be accessible at:
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`

### 4.4 Docker Containerization
Build and run the production container:
```bash
docker build -t asci-core:2.0.0 .
docker run -p 8000:8000 asci-core:2.0.0
```
Verify the container health endpoint:
```bash
curl http://localhost:8000/health
```

---

## 5. REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health status and corridor scope |
| `GET` | `/registry` | List all canonical entities and coordinates |
| `GET` | `/network` | Corridor graph nodes and topological edge count |
| `POST` | `/events` | Ingest disruption alert with gazetteer resolution |
| `GET` | `/events/{id}` | Retrieve structured event record |
| `POST` | `/events/{id}/plan` | Trigger Stage A–E walking skeleton planning loop |
| `GET` | `/plans/{id}` | Retrieve generated flow allocation plan |
| `GET` | `/traces/{id}` | Retrieve step-by-step operator trace and costs |

