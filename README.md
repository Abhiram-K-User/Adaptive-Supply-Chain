# Adaptive Supply Chain Intelligence Platform (ASCI)
## Integrated Agentic-RAG & Mathematical Optimization Control Tower (v2.0)
### South India Port-Hinterland Automotive Corridor

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2.10+-green.svg)](https://docs.pydantic.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Google OR-Tools](https://img.shields.io/badge/OR--Tools-GLOP%20LP-4285F4.svg)](https://developers.google.com/optimization)
[![SciPy HiGHS](https://img.shields.io/badge/SciPy-HiGHS%20Dual--Solver-8CAAE6.svg)](https://scipy.org)
[![React 18](https://img.shields.io/badge/frontend-React%2018%20%2B%20Vite%20%2B%20Tailwind-61DAFB.svg)](https://react.dev/)

The **Adaptive Supply Chain Intelligence Platform (ASCI)** converts multimodal disruption signals (cyclones, port strikes, highway flooding, customs bottlenecks) into mathematically verified, evidence-cited mitigation plans for Just-In-Time (JIT) automotive supply chains across South India.

---

## 1. Master Plans & Documentation Directory

The project follows a structured engineering hierarchy:

| Document | Role | Path |
| :--- | :--- | :--- |
| **Master Plan (PRD)** | Governing 9-Phase Product Contract & Formal Invariants | [`adaptive_supply_chain_intelligence_prd.md`](adaptive_supply_chain_intelligence_prd.md) |
| **Current Implementation Plan** | Prototype Demo Priorities & Placeholder Elimination | [`DEMO_NEXT_STEPS.md`](DEMO_NEXT_STEPS.md) |
| **Setup & Onboarding Guide** | Step-by-step installation, environment & build guide | [`docs/SETUP.md`](docs/SETUP.md) |
| **Architecture Specification** | 5-stage pipeline, LP dual-solver, & design tokens | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **REST API Reference** | Complete endpoint documentation, schemas & payloads | [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) |
| **Technical Context & Invariants** | Immutable state rules, USKL store contracts & history | [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) |
| **Milestone Roadmap** | PRD Gate G0–G5 status & immediate demo tasks | [`docs/ROADMAP.md`](docs/ROADMAP.md) |

---

## 2. Repository Structure

The repository is organized into distinct, clean modules:

```
Adaptive-Supply-Chain/
├── backend/                       # Python ASGI server entrypoint
│   ├── __init__.py
│   └── app/
│       ├── __init__.py
│       └── main.py                # FastAPI instance forwarding to asci.api.main
├── data/                          # USKL seed corpora and geo feeds
│   ├── feeds/                     # Sample and replay disruption feeds (GDACS, GDELT, RSS)
│   └── seeds/                     # Corridor topology definitions (v0_core, v1_corridor)
├── docs/                          # Comprehensive system documentation
│   ├── SETUP.md                   # Developer setup & onboarding instructions
│   ├── ARCHITECTURE.md            # 5-stage pipeline, LP dual-solver, & design tokens
│   ├── API_REFERENCE.md           # REST API endpoints & schemas
│   ├── PROJECT_CONTEXT.md         # Full technical invariants & data store specifications
│   └── ROADMAP.md                 # Master PRD milestones & current demo tasks
├── frontend/                      # React 18 + TypeScript + Vite + Tailwind CSS SPA
│   ├── dist/                      # Production build assets (served by backend)
│   ├── src/                       # React components, pages, contexts, & API client
│   ├── package.json
│   ├── tailwind.config.ts
│   └── vite.config.ts             # Vite dev server with proxy to :8000
├── scripts/                       # Operational and benchmarking scripts
│   ├── run_demo.py                # Single-command demonstration runner
│   └── run_suite_s1.py            # Statistical benchmark suite (Gate G2 validation)
├── src/asci/                      # Core ASCI Python package
│   ├── api/                       # FastAPI REST endpoints & static file mounting
│   ├── benchmarks/                # Suite S1–S4 benchmarking modules
│   ├── core/                      # Immutable PipelineState, contracts, canonical registry
│   ├── ingestion/                 # Multimodal adapters (GDACS, GDELT, Weather, PortWatch)
│   ├── llm/                       # Multi-provider LLM client & RAG briefing generator
│   ├── stages/                    # 5-Stage optimization pipeline (Stage A -> Stage E)
│   └── uskl/                      # Unified Supply Chain Knowledge Layer stores
├── tests/                         # Pytest test suite (116+ unit & integration tests)
├── adaptive_supply_chain_intelligence_prd.md # MASTER PLAN (Product Requirements Document)
├── DEMO_NEXT_STEPS.md             # CURRENT IMPLEMENTATION PLAN (Prototype Roadmap)
├── Dockerfile                     # Multi-stage container specification
├── pyproject.toml                 # Python package metadata & dependencies
├── requirements.txt               # Pinned Python requirements
└── README.md                      # Repository landing page
```

---

## 3. Quick Start

### 3.1. Prerequisites
- Python 3.11+
- Node.js 18+ & npm

### 3.2. Install Backend & Frontend

```bash
# 1. Python virtual environment & dependencies
python -m venv .venv
# Activate virtualenv (.venv\Scripts\activate on Windows, source .venv/bin/activate on Linux/Mac)
pip install -e .

# 2. Environment configuration
cp .env.example .env
# (Optional) Add your GROQ_API_KEY in .env for fast free LLM inference

# 3. Build frontend bundle
cd frontend
npm install
npm run build
cd ..
```

### 3.3. Run the Control Tower

```bash
# Start FastAPI server (serves both REST API and React UI on port 8000)
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Operational Control Tower UI**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive Swagger API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

For UI development with instantaneous Hot Module Reloading (HMR):
```bash
# In frontend directory:
npm run dev
# Open http://localhost:5173/ (proxies API requests to http://127.0.0.1:8000)
```

---

## 4. Key Architectural Highlights

### 4.1. 5-Stage Agentic Pipeline
1. **Stage A (Perception)**: Multimodal ingestion (GDACS, GDELT, IMD Weather, IMF PortWatch) with `<UNTRUSTED_DOCUMENT>` prompt injection boundaries.
2. **Stage B (Corridor Risk)**: Tier-1 BFS & Tier-2 BPR dynamic congestion propagation with Time-to-Line-Stop (TTLS) plant forecasts.
3. **Stage C (RAG Controller)**: Context-bounded vector retrieval (9 SOP playbooks) + time-series recovery curves.
4. **Stage D (Dual-Solver LP Optimizer)**: Multi-commodity flow allocation via **Google OR-Tools GLOP** primary LP solver independently verified by **SciPy HiGHS** dual-solver ($< 0.1\%$ gap).
5. **Stage E (Control Tower)**: Cytoscape network graph, Leaflet geospatial visualization, and citation-verified RAG executive briefing.

### 4.2. Dual-Theme Enterprise UI
- **Primary Dark Reference**: High-contrast black and charcoal layered dashboard with glowing SVG trajectory sparklines, capsule metric pills, and ambient depth.
- **Light Theme**: Crisp enterprise GDG theme with high readability and consistent semantic tokens.
- **Iconography**: 100% strict adherence to Lucide React SVG vectors (zero emojis).

---

## 5. Testing & Verification

```bash
# Run complete test suite (unit + integration)
pytest tests/ -v

# Run Gate G2 Suite S1 statistical benchmark
python scripts/run_suite_s1.py
```

See [`docs/SETUP.md`](docs/SETUP.md) for full developer onboarding instructions.
