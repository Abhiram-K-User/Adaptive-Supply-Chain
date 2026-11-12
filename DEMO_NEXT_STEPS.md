# ASCI Control Tower — Teammate Handoff & Next Steps for Prototype Demo

> **Purpose**: Master status tracking document for what is live in `asci-core/`, what was recently implemented, and the exact next steps for the **Prototype Demonstration** and future roadmap.
>
> **Companion Docs**: See [`project_context.md`](project_context.md) for architecture invariants and [`../adaptive_supply_chain_intelligence_prd.md`](../adaptive_supply_chain_intelligence_prd.md) for full product contracts.

---

## Executive Implementation Status Matrix

| Module / Milestone | Item | Status | Verification / Location |
|---|---|---|---|
| **Corridor Network** | Canonical Graph (`118` nodes / `364` edges) | ✅ LIVE | `registry.py`, `graph_store.py` (`v1_corridor`) |
| **Feed Ingestion** | GDACS, GDELT/RSS, Open-Meteo, PortWatch | ✅ LIVE | `POST /ingest/live`, `POST /ingest/replay`, `/feeds/status` |
| **Pipeline Core** | Stage A → E Optimization Pipeline | ✅ LIVE | Google OR-Tools + SciPy HiGHS dual solver |
| **Frontend UI/UX** | Industrial Enterprise Command Center | ✅ LIVE | React 18 + TS + Tailwind + Leaflet + Cytoscape |
| **Task 1A** | Interactive What-If Sandbox | ✅ **DONE** | `POST /whatif` + `WhatIfPlaceholderView.tsx` |
| **Task 1B** | Single Citation Drill-Down & Port Curves | ✅ **DONE** | `GET /evidence/{id}` + `EvidenceView.tsx` |
| **Task 1C** | Realized Outcomes & Loop L1 Calibration | ✅ **DONE** | `POST /outcomes` + `OutcomesMonitoringPlaceholderView.tsx` |
| **Task 1D** | Planner Decision Memory (Loop L2) Audit Log | ✅ **DONE** | `GET /decisions` + `OptimizationView.tsx` |
| **Task 1E** | Demo Persistence & Multi-Stage Dockerfile | ✅ **DONE** | `--data-dir ./local_data`, `--ephemeral`, `Dockerfile` |
| **Task 2A** | Deterministic vs. CVaR Comparison Breakdown | ✅ **DONE** | `OptimizationView.tsx` (Risk Hedging card) |
| **UI Polish** | Brand Logo Sync & Sidebar Text Overflow Fix | ✅ **DONE** | `BrandLogo.tsx`, `Sidebar.tsx`, `index.html` |
| **Task 2B** | Multi-Step Stage C Loop L2 Memory Reuse | 🔄 *NEXT* | `stage_c_controller.py` + `TraceView.tsx` |
| **Task 2C** | Gate G3 Remaining L3 Verifier Rules | 🔄 *NEXT* | `stage_d_optimiser.py` (Line-Stop & Churn checks) |
| **Phase 6–9** | Benchmark Suites S2–S6 & Background Daemon | ⏳ *DEFERRED*| Post-Demo roadmap |

---

## 1. What Was Just Completed (Eliminated All Major Placeholders)

### ✅ Task 1A: Interactive What-If Sandbox (`POST /whatif`)
- **Backend (`src/asci/api/main.py`)**:
  - Implemented `WhatIfRequest` & `WhatIfResponse` schemas.
  - Implemented `POST /whatif` which executes Stage B → Stage C → Stage D in-memory with custom capacity multiplier and duration without mutating persisted events or official plans.
  - Returns baseline cost vs. simulated cost deltas, unmet demand deltas, rail mode share shift, and L1–L3 verification status.
- **Frontend (`frontend/src/components/WhatIfPlaceholderView.tsx`)**:
  - Removed placeholder banner.
  - Added live port/ICD target selector, capacity multiplier slider (0–100%), duration slider (0.5–14d), and risk mode selector (`DETERMINISTIC`, `EXPECTED_COST`, `CVAR`).
  - Active **"Run Sensitivity Re-Optimization"** button displaying side-by-side KPI cards with color-coded delta badges.

### ✅ Task 1B: Single Citation Drill-Down & Port Recovery Curve (`GET /evidence/{id}`)
- **Backend (`src/asci/uskl/vector_store.py`, `src/asci/api/main.py`)**:
  - Added `SemanticVectorStore.get_document(citation_id: str) -> EvidenceItem | None`.
  - Added `GET /evidence/{citation_id}` returning full metadata (`trust_tier`, `publication_date`, `expires_at`, `supported_claims`, `entity_ids`) plus empirical port recovery trajectories from `TimeSeriesStore`.
- **Frontend (`frontend/src/components/EvidenceView.tsx`)**:
  - Clicking any citation card immediately fetches and displays detailed claim badges, target entity mappings, and visual day-by-day port recovery capacity bars (Day 1..5 → 20%..100%).

### ✅ Task 1C: Realized Outcomes Feedback (Loop L1) (`POST /outcomes`)
- **Backend (`src/asci/uskl/timeseries_store.py`, `src/asci/api/main.py`)**:
  - Extended `TimeSeriesStore` with `record_realized_outcome()` to blend real-world port throughput into empirical recovery curves and record daily observations.
  - Added `POST /outcomes` and `GET /outcomes/{entity_id}` endpoints.
- **Frontend (`frontend/src/components/OutcomesMonitoringPlaceholderView.tsx`)**:
  - Replaced the disabled placeholder with an active form: Port Selector, Observed TEU/day, Vessel Calls, Day Offset, and Hazard Type.
  - Live feedback banner confirms recovery curve recalibration and deviation percentage.

### ✅ Task 1D: Decision Memory Audit Log (Loop L2) (`GET /decisions`)
- **Backend (`src/asci/uskl/decision_store.py`, `src/asci/api/main.py`)**:
  - Added `list_recent_decisions(limit=20, plan_id=None)` in `DecisionTraceStore`.
  - Added `GET /decisions` endpoint.
- **Frontend (`frontend/src/components/OptimizationView.tsx`)**:
  - Embedded a **"Decision Memory Audit Log (Loop L2)"** table showing decision verdict badges (`APPROVE`, `EDIT`, `REJECT`), plan ID, operator ID, comments, and timestamps.
  - Auto-refreshes immediately after submitting an operator decision.

### ✅ Task 1E: Persistence Defaults & Multi-Stage Dockerfile
- **`scripts/run_demo.py`**: Defaulted `--data-dir` to `./local_data` and added `--ephemeral` flag for in-memory testing.
- **`.gitignore`**: Added `local_data/` to prevent committing SQLite databases.
- **`Dockerfile`**: Added Stage 0 (`node:22-alpine` builder) to compile `frontend/dist` before launching the Python runner.

### ✅ Task 2A: Deterministic vs. CVaR Comparison Breakdown Card
- **`frontend/src/components/OptimizationView.tsx`**: Added an expandable *"Compare vs Deterministic Baseline"* card showing why CVaR hedging is superior: a +12% nominal cost premium eliminates the catastrophic $18.4M line-stop risk during port disruption storms.

### ✅ UI/UX & Brand Consistency Fixes
- **Logo Synchronization**: Updated `BrandLogo.tsx` with a crisp network topology mark matching the system favicon in `index.html`.
- **Text Overflow Fix**: Eliminated text overflow in the sidebar's Corridor Network status box and Control Tower footer using proper `min-w-0` and truncation styling.

---

## 2. Immediate Next Steps (What To Do Next)

Here are the exact remaining items to tackle in order of impact:

### Step 1: Live Demo Verification & Scenario Rehearsal
Run the complete end-to-end launcher and verify the live interactive flow before presentation:
```bash
# PowerShell
$env:PYTHONPATH = "src"
python scripts/run_demo.py --scale v1_corridor --preload --data-dir ./local_data --open
```
**Demo Script Checklist**:
1. Click **"Run Cyclone Michaung Demo"** in top bar → observe Stage A entity resolution, Stage B propagation, Stage D OR-Tools allocation, and Stage E RAG briefing.
2. Navigate to **Optimization Engine** → click *"Compare vs Deterministic Baseline"* to demonstrate the CVaR risk-hedging value proposition.
3. In **Decision Memory Approval** tab → click *"Approve Plan to Memory"* → confirm the new decision immediately appears in the audit log table below.
4. Navigate to **What-If Sandbox** (via deep link or tab) → adjust the capacity slider (e.g. 20%) and duration (e.g. 5 days) → click *"Run Sensitivity Re-Optimization"* → observe instant in-memory cost and rail-share deltas.
5. Navigate to **Evidence & Playbooks** → click any `[CIT_PLAYBOOK_...]` card → observe metadata and the day-by-day port recovery curve bars on the right rail.
6. Navigate to **Demand Forecasting** → test the **Loop L1: Realized Outcomes** form by recording 4,500 TEU for `PORT_CHENNAI` → observe real-time multiplier recalibration.

---

### Step 2: Task 2B — Multi-Step Stage C Agentic Loop & Loop L2 Memory Reuse
* **Priority**: High (Elevates demo from static 5-step pipeline into visible Agentic-RAG).
* **Backend (`src/asci/stages/stage_c_controller.py`)**:
  - Query past `APPROVE`/`EDIT` constraints from `DecisionTraceStore` for the active corridor/hazard (`RETRIEVE_DECISIONS`).
  - Inject those historical decisions into the scenario context so past planner overrides actively steer optimization.
  - Split Stage C trace items into explicit reasoning steps (`RETRIEVE_TEXT` → `GRADE` → `REWRITE_QUERY` → `RETRIEVE_TS` → `RETRIEVE_DECISIONS` → `SYNTHESIZE_SCENARIOS`).
  - *Coordination Rule*: Update `tests/integration/test_walking_skeleton.py` to match the updated operator step count.

---

### Step 3: Task 2C — Gate G3 Remaining L3 Verifier Rules
* **Priority**: Medium.
* **Backend (`src/asci/stages/stage_d_optimiser.py`)**:
  - `L3: LINE_STOP_SAFETY_THRESHOLD`: Escalate when a critical assembly plant drops below safe buffer cover margin despite unused corridor capacity remaining elsewhere.
  - `L3: PLAN_CHURN_LIMIT`: Compare flow allocations against the prior active plan for the same event to prevent erratic plan oscillations.
* **Backend (`src/asci/llm/explainer.py`)**:
  - Add `strict_citation_gate=True` mode that flags or escalates numerical claims not backed by ground-truth evidence snippets.

---

### Step 4: Docker Container Build Verification
Verify the multi-stage Docker build produces a self-contained production image:
```bash
docker build -t asci-control-tower:v2.0 .
docker run -p 8000:8000 asci-control-tower:v2.0
# Test in browser: http://localhost:8000/
```

---

## 3. Post-Demo Items (Deferred to Phases 6–9)

Do **not** block the prototype demonstration on these long-range tasks:
- **Phase 6 (Gate G4)**: PyTorch Masked MLP Policy / DAgger Training (the deterministic budget controller currently handles all routing rules cleanly).
- **Phase 7–8**: Benchmark Suites S2 (Cascading Spillover), S3 (Prompt-Injection Red-Team), S4 (Randomized Faults), and S6 (Cyclone Michaung Historical Replay).
- **Phase 8**: Always-on OS-level cron daemon for autonomous background polling (the top bar **"Poll Live Feeds"** + **"Auto 60s"** toggle handles all demo needs interactively).

---

## 4. Verification & Testing Commands

```bash
# 1. Run unit test suite for newly added DEMO endpoints (FastAPI TestClient)
$env:PYTHONPATH = "src"
python -m pytest tests/unit/test_demo_next_steps_api.py -v

# 2. Run backend-frontend integration verification (all 9 checks)
python scripts/verify_backend_frontend_connection.py

# 3. Build React frontend bundle
cd frontend
npm run build
cd ..

# 4. Run full test suite
python -m pytest tests/ -q
```
