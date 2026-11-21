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
│   ├── benchmarks/                # Suites S1–S6 and nine ablation studies
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

Install the declared dependencies before running: ASCI requires SciPy 1.15.3 or later. SciPy 1.15.0–1.15.2 repeatedly copied HiGHS result arrays, causing a substantial `linprog` performance regression even after an optimal solve. The [upstream fix in 1.15.3](https://docs.scipy.org/doc/scipy-1.15.3/release/1.15.3-notes.html) removes that overhead. ASCI retains the original independent solver verification and two-second S1 P95 test threshold.

```bash
# Windows PowerShell:
$env:PYTHONPATH = "src"
python scripts/run_suite_s1.py

# Linux / macOS:
PYTHONPATH=src python scripts/run_suite_s1.py
```

---

### 6.3. Run Suite S2 Multi-Day Compound Timelines

Suite S2 exercises the existing event store, graph analysis, controller, OR-Tools optimizer, HiGHS verifier, and dashboard serializer. It uses isolated in-memory stores and never modifies the running application's data.

```bash
# Required seven-day, ten-case verification on the full corridor
python scripts/run_suite_s2.py --days 7 --cases 10

# Verify both topologies and save an explicit report
python scripts/run_suite_s2.py --days 7 --cases 10 --scale both --output artifacts/suite_s2_report.json
```

Each case follows the same lifecycle with different seeded port/junction pairs, severities, and confidence values:

| Day offset | Operation | Expected active disruptions |
| --- | --- | --- |
| 0 | Introduce a weather bulletin | Weather |
| 1 | Introduce a road disruption | Weather + road |
| 2 | Escalate the weather severity | Weather + road |
| 3 | Retract the weather bulletin | Road |
| 4 | Reopen the road | None |
| 5 | Reopen weather with a lower severity and one-day duration | Revised weather |
| 6 | Expire the revised weather bulletin | None |
| 7 onward, when requested | Observe recovery | None |

Every daily snapshot is independently recomputed twice. Planning uses each bulletin's remaining duration at that day; the event store retains the original reported timestamp and duration. The report includes lifecycle and revision checks, capacity clearance, complete numerical fingerprints, trace/cost accounting, verification failures, case definitions, and the full effective pipeline configuration. A zero exit code requires every benchmark check to pass. Unavoidable physical shortages are counted separately: L3 still rejects those plans, while the benchmark checks that mathematical constraints were respected. Exit code `1` signals failed benchmark checks; `2` signals invalid input, I/O, or an execution error that prevented the report from being completed.

The default seed is `42`; use `--seed` to change it. `--start` accepts a timezone-aware ISO timestamp. The default report is `artifacts/suite_s2_report.json`, written atomically. To repeat exact inputs, save a report's `case_definitions` array as a JSON file and pass `--case-file path/to/cases.json`; the case count defaults to that array's length. Case files validate canonical entity types, unique IDs, severity bounds, and escalation/revision ordering.

Use `--pipeline-config path/to/config.json` to supply existing `PipelineConfig` settings, for example `{"risk_mode": "CVAR", "propagation_tier": 1}`. CLI scale and seed override values from that file. Unknown configuration keys are rejected, and live LLM calls are disabled for offline reproducibility.

Compound snapshots take the minimum residual capacity across their active events. Scenario branches use an explicitly independent joint probability distribution and are bounded by `--max-joint-scenarios` (default `256`, at least `9` for this two-event suite). Per-event congestion and TTLS estimates are composed conservatively; this benchmark does not claim to simulate the interactions of multiple queueing systems. The synthetic incidents are benchmark inputs; the resulting plans and verification outcomes are computed by the actual implementation.

### 6.4. Historical Michaung Replay (S6)

```bash
python scripts/run_suite_s6.py --scale both --output local_data/review/suite_s6_report.json
```

The default cache contains 90 genuine daily IMF PortWatch observations for Chennai (Madras) and Kamarajar Port, 1 November–15 December 2023. The runner uses 30 November as the baseline cutoff and freezes the forecast origin at 3 December. It evaluates 26 port-days per topology. `--history` selects another checksum-validated cache; `--config` accepts `SuiteS6Config` JSON (baseline dates, horizon, initial capacity/duration assumptions, disruption threshold and seed). Missing dates, duplicate keys, nonfinite measurements and checksum mismatches fail validation. Reports distinguish measured vessel calls from modelled capacity ratios. PortWatch cargo tonnage is never labelled TEU.

This is retrospective alignment: the existing recovery prior has no independently documented training provenance. Reported lead time uses an assumed origin, not a recorded live forecast timestamp. Neither the code nor the report claims a leakage-free historical model training process. Future observations are used only to score forecasts; a dedicated mutation test verifies they cannot alter predictions or the pre-event baseline. Refreshing the public cache is an explicit online operation through `scripts/cache_michaung_portwatch.py`; normal replay performs no downloads.

### 6.5. Nine Phase 8 Ablation Studies

```bash
# First collection uses real configured LLM calls for the planner comparison.
python scripts/run_ablations.py --record-llm --output-dir local_data/review/ablations

# Subsequent runs replay exact recorded inputs without provider calls.
python scripts/run_ablations.py --output-dir local_data/review/ablations

# Focus a comparison or supply a validated study design.
python scripts/run_ablations.py --studies 3,4,5 --cases 12 --scale both
python scripts/run_ablations.py --config path/to/study-design.json
```

The default design uses 12 seeded paired core anchors per topology, three lambda values and seven independent held-out scenario realizations per event. `AblationConfig` controls case count, seed, bootstrap samples, budgets, retrieval depth, sufficiency threshold, holdout size, risk quantile, target thresholds and planner cache directory. Unknown configuration fields, empty/duplicate/out-of-range budgets and nonfinite values are rejected. JSON reports retain raw per-case data, bootstrap 95% mean confidence intervals (controller lambda repeats clustered by event), model assumptions and limitations; `summary.csv` provides measured table rows. Execution errors return exit 2 and write `failure.json`; incomplete comparisons return 1. Research targets that are not met remain false in a successfully completed report: exit 0 means valid evaluation, not that every thesis hypothesis was confirmed.

| Study | What is actually compared and scored |
| --- | --- |
| 1 | No graph versus two-hop graph; affected-path recall and exposure-weighted bottleneck loss error against a declared five-hop dynamic reference. |
| 2 | Real no-RAG, fixed-RAG and rule-based agentic rollouts; paired held-out regret and measured nondominated operator-cost frontiers. No interpolated cost matches are invented. |
| 3 | Text, graph metadata, and graph plus past recovery-profile retrieval over an independently labelled planted analogue corpus; Recall@k and context precision. |
| 4 | Current citation ID checking versus no checking on supported claims and independent mutations. A valid ID does not prove entailment; unsupported prose is counted even when the citation exists. |
| 5 | Sufficiency-gated expansion versus fixed retrieval count; executed retrieval, recovery lookup, rewrite and grading steps, top-ranked analogue correctness and ECE of the raw coverage heuristic. |
| 6 | Always-full, rule, genuine LLM planner and learned MLP rollouts; operator cost, latency, held-out deeper-analysis benefit labels, tie-aware AUROC and ECE. Single-class AUROC is undefined and reported null. |
| 7 | Hop-decay and dynamic redistribution versus the expanded dynamic reference; top-10 delayed-node recall, delay error, secondary capacity-multiplier error and Stage B runtime. Capacity attenuation is shared by both engines and cannot by itself measure congestion differences. No optional GNN was built. |
| 8 | Deterministic and CVaR plans trained on the same scenarios, evaluated on separate holdouts; 95th-percentile regret, mean realized model cost, shortfall, soft spill and line-stop slack. |
| 9 | Genuine historical PortWatch alignment from S6, including MAE, direction agreement, rank correlation and assumed-origin lead time. |

Regret is fixed-plan cost minus a hindsight optimum verified by OR-Tools and HiGHS under the same graph/cost model. The public optimizer evaluator uses the actual unmet, spill and line-stop penalties. The LP uses soft scenario capacity spill penalties, not physical queueing or dispatch recourse. Synthetic studies do not establish real-world causal accuracy. Bootstrap intervals describe the seeded case sample and do not include uncertainty about data provenance or modelling assumptions.

Comparable regret permits at most the configured relative increase in mean regret versus always-full (default 1%); a zero-regret baseline permits only numerical tolerance. Compute units are Stage C's existing operator cost schedule, not API dollars or total machine energy. Planner call counts and original provider latency are retained; operator savings alone exclude LLM inference overhead and must not be cited as total compute savings. The LLM cache stores actual model/provider, complete prompts, input and response checksums, response text and latency. It never accepts a deterministic fallback as a planner result. Missing replay records fail unless `--record-llm` explicitly enables collection. Keep this cache with the reports for reproducibility; it contains benchmark state features, not API credentials.

Open **Analytics & Reports → Phase 8 Benchmark Results** to read the measured artifacts, compare scales and download full JSON. `ASCI_EVALUATION_DIR` configures the read-only report directory (default `local_data/review/ablations`). Missing, oversized or corrupt artifacts produce explicit API errors; the website never invents passing metrics or runs expensive evaluations on request. This Phase 8 CLI does not implement Phase 9's Docker master runner, thesis figures or final Gate G5 sign-off.

### 6.6. Standing Ingestion Worker

```bash
# Strict live polling; configure ASCI_WEBHOOK_URL in the service environment.
python scripts/run_ingestion_daemon.py --data-dir local_data --scale v1_corridor --interval 60

# One bounded live poll, or explicitly isolated replay verification.
python scripts/run_ingestion_daemon.py --data-dir local_data --once
python scripts/run_ingestion_daemon.py --data-dir local_data/worker-replay --once --replay
```

The worker polls GDACS and PortWatch independently, validates canonical entities, expires stale events and suppresses replay on live failures before it can write observations. PortWatch queries actual port identifiers and a bounded recent date window, with rolling vessel-call anomaly detection. Live TEU volume is unavailable and stored as null with a vessel-calls-only source marker; the alert text makes no measured-TEU claim. Vessel-only updates preserve any previously measured TEU for that day and its separate `teu_source`; a newly measured zero is still accepted as a real observation.

An OS file lock enforces one worker per data directory. SQLite commits the event update, stable content digest and durable webhook outbox in one transaction. Repeated content is deduplicated across restart; revised content updates the existing event lifecycle. The outbox retains the original destination across configuration changes. Non-2xx responses remain queued with capped exponential retry. Delivery is at least once: receivers must deduplicate the `Idempotency-Key` header. There is no destructive retry limit silently discarding alerts. Do not put credentials in webhook URLs; use an HTTPS endpoint in deployment.

`--webhook-batch-size`, `--webhook-timeout`, `--retry-base-seconds` and `--retry-max-seconds` configure delivery. SIGINT/SIGTERM stop between bounded network operations and interrupt interval waits. A single synchronous HTTP operation can take its configured timeout. No external alerts are sent by the verification suite; delivery is exercised against a local HTTP server.

Linux: adapt `deploy/asci-ingestion.service` paths, create the dedicated user/data directory and configure `/etc/asci/ingestion.env`, then explicitly install/enable the unit. Windows: `deploy/install-ingestion-task.ps1 -PythonPath <absolute-python.exe> -DataDirectory <absolute-data-dir> -WhatIf` previews a startup task; omit `-WhatIf` to register it when deployment is intended. The task uses machine/user environment settings, supports restart and prevents parallel instances. Registration at system startup may require administrator privileges. No permanent startup service is installed by development verification. Stop a foreground worker with Ctrl+C; remove a Windows task with `Unregister-ScheduledTask`, or disable the systemd unit when decommissioning.

### 6.7. Phase 8 Engineering Handoff

Phase 8 implementation is complete. `TASKS.md` leaves three Phase 9 tasks for the team: the Docker master benchmark/figure runner, the full UI rehearsal and freeze, and final offline Gate G5 verification. The existing Dockerfile has not received that final sign-off.

The verified checkpoint includes 197 passing tests, 255 exhaustive S1 cases, 140 passing S2 daily snapshots, 52 scored S6 port-days and all 18 ablation reports. Five additional concurrent API/restart cycles covered 15 episodes. Chromium verified both network sizes, target outcomes, JSON download integrity, selected-tab contrast in both themes and zero JavaScript page errors. Failed research targets remain measured outcomes: retrieval cost, semantic claim support, adaptive AUROC/calibration and the full-corridor propagation gain miss their thresholds. Read each report's limitations before using the numbers in a thesis or deployment decision.

**Source versus local evidence:** Git includes the implementation, tests, deployment templates and genuine historical cache in `data/seeds/cyclone_michaung_historical.json`. Generated reports, databases, logs, model/provider caches and `.env` remain local and ignored. On this workstation, `local_data/review/phase8-review.json` lists the verification evidence and changed files; measured reports and CSV are in `local_data/review/ablations`, and genuine planner recordings are in `local_data/llm_planner_cache`. Preserve the reports and planner recordings together when handing evidence to the team. They are required for exact offline ablation replay and are not supplied by a fresh Git checkout.

On a fresh checkout, install the declared dependencies and follow sections 6.1–6.6. To create missing LLM planner recordings, configure a supported real provider and explicitly run the ablation command with `--record-llm`; subsequent runs use cache-only replay. To display existing verified reports, set `ASCI_EVALUATION_DIR` to their directory before starting the API. Missing reports or cache entries produce explicit errors. Phase 9 owns packaging these artifacts for the final offline container run.

The local review application uses replay data in `local_data/review`; the live ingestion worker uses the separate `local_data/review/ingestion-live` directory so live bulletins do not change the reviewed scenarios. In a shared deployment, use the same intended data directory for the API and worker. No permanent startup task or external webhook destination was installed during verification.

Known environment notes are recorded in the local review report: three SWIG deprecation warnings, Vite's existing large-chunk warning, unrelated globally installed package conflicts and two pre-existing E402 imports in the legacy `backend/app/main.py` bootstrap. The configured lint scope (`src tests scripts`) passes. An initial non-terminating Windows native diagnostic did not recur in the concurrency checks or the clean final full regression run; its cause was not established.

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
ASCI verifies Google OR-Tools GLOP solutions independently with SciPy HiGHS. If `L2:DUAL_SOLVER_AGREEMENT` fails, check that both solvers satisfy the declared dependencies (`ortools>=9.10`, `scipy>=1.15.3`).

### Missing API Keys
ASCI includes a 100% deterministic offline fallback extractor and briefing generator. If no LLM API keys (`GROQ_API_KEY`, etc.) are configured, the platform automatically falls back to grounded deterministic heuristics without failing.

