# ASCI Setup & Developer Onboarding Guide

> **Adaptive Supply Chain Intelligence (ASCI) Platform**  
> Integrated Agentic-RAG & Mathematical Optimization Control Tower (v2.0)

---

## 1. System Requirements & Prerequisites

Ensure the following environments are installed on your host system:

| Component | Minimum Version | Recommended | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11+ | 3.11, 3.12, or 3.13 | Python 64-bit with pip |
| **Node.js** | 18.0.0+ | 20 LTS or 22 LTS | Required for React frontend build |
| **npm** | 9.0.0+ | 10+ | Bundled with Node.js |
| **OS** | Windows 10/11, macOS, Linux | Any | Fully tested on Windows 11 & Ubuntu 22.04 |
| **RAM** | 4 GB | 8 GB+ | For OR-Tools GLOP & HiGHS dual solver |

---

## 2. Repository Layout

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
│   ├── SETUP.md                   # This setup guide
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

## 3. Backend Environment Setup

### 3.1. Clone and Create Virtual Environment

```bash
git clone https://github.com/Abhiram-K-User/Adaptive-Supply-Chain.git
cd Adaptive-Supply-Chain

# Create a virtual environment (Python 3.11+)
python -m venv .venv

# Activate the virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows Command Prompt:
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

### 3.2. Install Python Dependencies

```bash
# Install package in editable development mode
pip install -e .

# Or install from requirements.txt
pip install -r requirements.txt
```

> **Key Python Dependencies**:
> - `fastapi`, `uvicorn`, `pydantic>=2.0` (REST API & Schemas)
> - `ortools>=9.8` (Google OR-Tools GLOP linear programming solver)
> - `scipy>=1.11` (HiGHS dual-solver mathematical verifier)
> - `networkx>=3.0` (Graph topology, betweenness, k-hop BFS)
> - `pytest>=7.0`, `hypothesis>=6.90` (Property-based test suite)
> - `httpx`, `feedparser` (Live feed ingestion)

### 3.3. Environment Variables Configuration

Copy the example environment template to `.env`:

```bash
# Windows PowerShell:
Copy-Item .env.example .env

# Linux / macOS / Git Bash:
cp .env.example .env
```

Open `.env` in your editor and configure as desired:

```ini
# LLM Providers (Optional for offline deterministic fallback; Groq recommended for free fast inference)
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Active LLM Provider Selection: "auto", "groq", "gemini", "openai", "ollama", or "deterministic"
ASCI_LLM_PROVIDER=auto

# Topology Scale: "v0_core" (23 nodes / 42 links) or "v1_corridor" (118 nodes / 364 links)
ASCI_NETWORK_SCALE=v1_corridor

# Persistent Storage Path (Optional: leaves empty for in-memory SQLite)
ASCI_DATA_DIR=./local_data

# Live Feeds Configuration
ASCI_LIVE_FEEDS_ENABLED=true
ASCI_LIVE_POLL_INTERVAL_SECONDS=0
```

---

## 4. Frontend Setup & Build

The frontend is built with React 18, TypeScript, Tailwind CSS, Lucide React, and Cytoscape.js.

### 4.1. Install Node Dependencies

```bash
cd frontend
npm install
```

### 4.2. Build Production Bundle

To build the static distribution that the FastAPI backend serves at `http://127.0.0.1:8000/`:

```bash
npm run build
```

The output bundle will be generated in `frontend/dist/` (HTML, CSS, and minified JS).

---

## 5. Running the Application

There are two primary ways to run ASCI:

### Option A: Production Full-Stack Mode (Single Port 8000)

Run the FastAPI backend with uvicorn. It will automatically serve both the REST API endpoints and the built React SPA frontend:

```bash
# From repository root:
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Web Dashboard**: Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.
- **Interactive Swagger API Docs**: Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- **Alternative ReDoc API Docs**: Open [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

### Option B: Frontend Hot-Reload Development Mode (Port 5173 + Port 8000)

When developing the UI with instantaneous Hot Module Replacement (HMR):

1. **Terminal 1 (Backend)**:
   ```bash
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. **Terminal 2 (Frontend)**:
   ```bash
   cd frontend
   npm run dev
   ```

- Open [http://localhost:5173/](http://localhost:5173/).
- All API requests to `/health`, `/events`, `/plans`, `/network`, `/feeds`, etc., are automatically proxied by Vite to `http://127.0.0.1:8000`.

### Option C: Standalone Interactive Demo Script

To run the automated scenario runner with preloaded disruptions and live browser launch:

```bash
# Windows PowerShell:
$env:PYTHONPATH = "src"
python scripts/run_demo.py --scale v1_corridor --preload --data-dir ./local_data --open

# Linux / macOS:
PYTHONPATH=src python scripts/run_demo.py --scale v1_corridor --preload --data-dir ./local_data --open
```

---

## 6. Running Tests & Verifications

ASCI maintains a 100% green test suite covering unit math models, LP dual-solver agreement, ingestion sanitization, and end-to-end pipelines.

### 6.1. Run Pytest Suite

```bash
# Run all unit and integration tests
pytest tests/ -v

# Run with short summary
pytest tests/ -q
```

### 6.2. Run Suite S1 Statistical Benchmarks (Gate G2 Validation)

To reproduce the multi-scenario Monte Carlo benchmark verifying OR-Tools GLOP vs. SciPy HiGHS convergence:

```bash
# Windows PowerShell:
$env:PYTHONPATH = "src"
python scripts/run_suite_s1.py

# Linux / macOS:
PYTHONPATH=src python scripts/run_suite_s1.py
```

---

## 7. Docker Deployment

A multi-stage `Dockerfile` is provided for containerized deployment:

```bash
# Build the Docker image
docker build -t asci-platform:latest .

# Run the container exposing port 8000
docker run -p 8000:8000 -e ASCI_NETWORK_SCALE=v1_corridor asci-platform:latest
```

Access the application at `http://localhost:8000/`.

---

## 8. Troubleshooting & Common Questions

### `EPERM` or `mkdir` on Windows during `npm install`
On Windows, occasional antivirus file locking can trigger transient `EPERM` errors. Re-run `npm install` or clear npm cache (`npm cache clean --force`).

### Dual-Solver Discrepancy Error
ASCI runs Google OR-Tools GLOP and SciPy HiGHS concurrently. If `L2:DUAL_SOLVER_AGREEMENT` fails, check that both solvers are installed with matching versions (`ortools>=9.8`, `scipy>=1.11`).

### Missing API Keys
ASCI includes a 100% deterministic offline fallback extractor and briefing generator. If no LLM API keys (`GROQ_API_KEY`, etc.) are configured, the platform automatically falls back to grounded deterministic heuristics without failing.

