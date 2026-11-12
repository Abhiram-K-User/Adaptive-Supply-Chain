# ASCI Control Tower — Teammate Handoff & Next Steps for Prototype Demo

> **Purpose**: Actionable engineering checklist for what is already live in `asci-core/` and what needs to be implemented next to make the **Prototype Demonstration** 100% end-to-end with zero remaining UI placeholders.
>
> **Companion Docs**: See [`project_context.md`](project_context.md) for architecture invariants and [`../adaptive_supply_chain_intelligence_prd.md`](../adaptive_supply_chain_intelligence_prd.md) for full product contracts.

---

## 1. What Already Works Today (Do Not Rebuild)

Before picking up new tasks, here is what is already implemented, integrated, and passing verification (**`127/127` pytest passing**, `ruff check src tests scripts` clean, Vite React TypeScript build clean):

1. **Corridor Network & Registry (`v0_core` & `v1_corridor`)**:
   - Canonical entities & graphs (`23` nodes / `42` edges for `v0_core`; `118` nodes / `364` edges for `v1_corridor`) in `src/asci/core/registry.py` and `src/asci/uskl/graph_store.py`.
2. **Real Live Data + Offline Replay Fallback (`src/asci/ingestion/`, `src/asci/api/main.py`)**:
   - `POST /ingest/live`, `POST /ingest/replay`, and `GET /feeds/status` poll **GDACS** (global disaster GeoJSON + 220 km coastal port fallback in `stage_a_events.py`), **GDELT / Google News India RSS** (filtered by disruption keywords + deterministic SHA-1 IDs), **Open-Meteo** (live 6-hub South India weather telemetry), and **IMF PortWatch** (with clean CSV sample fallback).
3. **End-to-End 5-Stage Optimization Pipeline (`Stage A -> E`)**:
   - **Stage A (`stage_a_events.py`)**: Prompt-injection sanitization (`quote_untrusted_text`), entity resolution, optional LLM extractor (`enable_llm=true`).
   - **Stage B (`stage_b_graph.py`, `stage_b_propagate.py`)**: Tier-1 BFS & Tier-2 BPR congestion propagation + Time-to-Line-Stop (`TTLS`) plant risk forecast.
   - **Stage C (`stage_c_controller.py`)**: Metadata-filtered playbook vector retrieval (`SemanticVectorStore`, 9 curated SOPs) + `TimeSeriesStore` recovery curve scenario synthesis.
   - **Stage D (`stage_d_optimiser.py`)**: Multi-commodity LP (`POWERTRAIN_CKD`, `EV_BATTERY_PACKS`, `BODY_CHASSIS_PARTS`) via **Google OR-Tools (`GLOP`) + SciPy HiGHS dual verification**, `DETERMINISTIC` / `EXPECTED_COST` / `CVAR` risk modes, and L1–L3 math checks.
   - **Stage E (`stage_e_dashboard.py`, `src/asci/llm/explainer.py`)**: Cytoscape/Map payload serialization + citation-checked RAG executive briefing (Groq/Gemini/OpenAI/Ollama or grounded offline fallback).
4. **React + TypeScript + Tailwind + Leaflet + Cytoscape UI (`frontend/`)**:
   - Served directly at `http://127.0.0.1:8000/` via built `frontend/dist/`.
   - Live interactive **India Geographic Map (Esri Dark Gray + OSM, zero API keys)** and **Cytoscape Graph** toggle, live feed badges + 6-hub weather strip, event injection/presets, diversion allocation table, plant line-stop table, L1–L3 verifier checks, session trace viewer (`TraceView.tsx`), evidence corpus search (`EvidenceView.tsx`), and Loop L2 planner sign-off (`POST /decisions`).

---

## 2. Priority 1 — Prototype Demo Must-Haves (Eliminate UI Placeholders)

Right now, the React UI intentionally marks unbuilt backend features with amber **"Placeholder"** badges so the demo stays 100% honest. Completing the **4 endpoints + UI wiring** below removes every major placeholder in the live dashboard.

### Task 1A: Interactive What-If Sandbox (`POST /whatif`)
- **Lane**: `M3` (API) + `M4` (Frontend)
- **Where the placeholder is**: `frontend/src/components/WhatIfPlaceholderView.tsx` (currently has sliders + locked button)
- **Backend work (`src/asci/api/main.py`)**:
  - Add `WhatIfRequest` schema:
    ```python
    class WhatIfRequest(BaseModel):
        event_id: str | None = None
        target_entity_id: str
        capacity_multiplier: float = Field(ge=0.0, le=1.0)
        duration_days: float = Field(gt=0.0, le=30.0)
        risk_mode: Literal["DETERMINISTIC", "EXPECTED_COST", "CVAR"] = "CVAR"
        propagation_tier: Literal[1, 2] = 2
        baseline_plan_id: str | None = None
    ```
  - Run `Stage B -> Stage C -> Stage D` **strictly in-memory without mutating `event_store` or saving a fake official plan unless flagged**, overriding the target node's capacity multiplier and duration.
  - Return baseline vs. simulated deltas: `simulated_plan`, `verification`, `cost_delta`, `unmet_demand_delta_teu`, `rail_share_delta_pct`, and per-plant `ttls_delta_days`.
- **Frontend work (`frontend/src/api/client.ts`, `WhatIfPlaceholderView.tsx` -> `WhatIfView.tsx`)**:
  - Enable the `"Run Sensitivity Re-Optimization"` button and render real baseline vs. simulated KPI cards + delta badges.
- **Verification**: Add FastAPI integration test verifying `POST /whatif` returns valid deltas and leaves `GET /events` & `decisions.db` unchanged.

---

### Task 1B: Single Citation Drill-Down & Port Recovery Curve (`GET /evidence/{id}`)
- **Lane**: `M3` (USKL + API) + `M4` (Frontend)
- **Where the placeholder is**: `frontend/src/components/EvidenceView.tsx` right rail (`Single Citation Drill-Down`)
- **Backend work**:
  - Add `SemanticVectorStore.get_document(citation_id: str) -> EvidenceItem | None` in `src/asci/uskl/vector_store.py`.
  - Add `GET /evidence/{citation_id}` in `src/asci/api/main.py` (`404` if not found), returning:
    - Full `EvidenceItem` metadata (`trust_tier`, `publication_date`, `expires_at`, `untrusted_quoted`, `supported_claims`, `entity_ids`, content hash)
    - Linked port recovery curve points from `TimeSeriesStore.get_recovery_curve(entity_id, hazard_type)` for any matching `PORT` entity IDs on that citation.
- **Frontend work (`frontend/src/components/EvidenceView.tsx`, `OverviewCommandView.tsx`)**:
  - Fetch `GET /evidence/{id}` when clicking a document card (or clicking `[CIT_...]` inside the RAG briefing), displaying full metadata, claim badges, and a visual day-by-day recovery capacity chart (`Day 1..5 -> 10%..100%`).

---

### Task 1C: Realized Outcomes & Loop L1 Calibration (`POST /outcomes`)
- **Lane**: `M3` (USKL + API) + `M4` (Frontend)
- **Where the placeholder is**: `frontend/src/components/OutcomesMonitoringPlaceholderView.tsx` (`Loop L1: Realized Outcomes` card)
- **Backend work**:
  - Extend `src/asci/uskl/timeseries_store.py` (already stores `port_baselines`, `recovery_curves`, `daily_port_observations`) with an update helper `record_realized_outcome(entity_id, hazard_type, day_offset, observed_teu, vessel_calls, obs_date)` that logs the observation and blends/updates the empirical `recovery_curves` multiplier (`observed_teu / baseline.daily_teu_capacity`).
  - Add `POST /outcomes` in `src/asci/api/main.py` returning updated recovery curve + baseline comparison metrics (`observed_teu`, `baseline_teu`, `realized_multiplier`, `deviation_pct`).
  - Optionally add `GET /outcomes/{entity_id}` so the UI shows current baseline + recovery trajectory before and after submission.
- **Frontend work (`OutcomesMonitoringPlaceholderView.tsx`)**:
  - Replace the disabled Loop L1 button with a working form (`Port Selector`, `Observed TEU/day`, `Vessel Calls`, `Day Offset`, `Hazard Type`) showing live baseline vs. realized recalibration so judges can see **Closed Feedback Loop L1** update `TimeSeriesStore` in real time.

---

### Task 1D: Visible Planner Decision Memory History (`GET /decisions`)
- **Lane**: `M3` (USKL + API) + `M4` (Frontend)
- **Why it matters for demo**: Today `POST /decisions` saves `APPROVE | EDIT | REJECT` to SQLite (`DecisionTraceStore`), and the UI shows a toast banner, but refreshing or switching plans doesn't display the saved decision audit log on screen.
- **Backend work**:
  - Add `list_recent_decisions(limit: int = 20, plan_id: str | None = None)` in `src/asci/uskl/decision_store.py`.
  - Add `GET /decisions` (optional `?plan_id=...` & `?limit=...`) in `src/asci/api/main.py`.
- **Frontend work (`OverviewCommandView.tsx`)**:
  - Render a compact **"Recent Decision Memory (Loop L2)"** list directly below the `Approve / Edit Plan / Reject` buttons showing planner ID, verdict badge, timestamp, and modification JSON.

---

### Task 1E: Demo Persistence Default & Multi-Stage Frontend Docker Build
- **Lane**: `M5` (Delivery)
- **Why it matters**:
  1. `scripts/run_demo.py` leaves `--data-dir` unset unless passed, causing SQLite to run `:memory:` (clearing decisions/events on restart). Default `--data-dir` in `run_demo.py` to `./local_data` (or document/add an `--ephemeral` flag) and add `local_data/` to `.gitignore`.
  2. `Dockerfile` currently uses only `python:3.11-slim` and does **not** run `npm run build` in `frontend/`, so a clean Docker build would fall back to the legacy `src/asci/ui/dashboard.html` unless `frontend/dist` was copied in. Add a `node:22-alpine` builder stage in `Dockerfile` copying `frontend/dist` into `/app/frontend/dist`, plus `COPY scripts /app/scripts` if needed for demo/benchmark runs.

---

## 3. Priority 2 — High-Impact Differentiators (If Time Permits Before Demo)

Once Priority 1 is done, these 3 upgrades elevate the prototype from a working solver + dashboard into a full research-grade **Agentic-RAG** system:

### Task 2A: Deterministic vs. CVaR + RAG Comparison Card (Low Effort, High Demo Impact)
- **Why**: Judges always ask *"Why is CVaR + Agentic-RAG better than normal shortest-path routing?"*
- **What to build**: Add a `"Compare vs Deterministic Baseline"` button in `OverviewCommandView.tsx` (reusing `/events/{id}/plan` with `risk_mode="DETERMINISTIC"` vs `risk_mode="CVAR"`), displaying side-by-side `Expected Cost`, `Worst-Case CVaR Cost`, `Rail Shift %`, and `Unmet Demand TEU`.

### Task 2B: Multi-Step Stage C Agentic Loop & Loop L2 Memory Reuse
- **Lane**: `M1` (`src/asci/stages/stage_c_controller.py`, `src/asci/stages/__init__.py`)
- **What exists**: `StageCController` currently runs inside 1 operator step (enforced by Gate G1's 5-step trace test).
- **What to add**:
  - Add `RETRIEVE_DECISIONS` so past `APPROVE`/`EDIT` constraints from `DecisionTraceStore` for the same corridor/hazard are retrieved and injected into scenario/playbook context (actually closing **Loop L2** in reasoning, not just logging it).
  - Split Stage C into iterative trace steps (`RETRIEVE_TEXT` -> `GRADE` -> `REWRITE_QUERY` -> `RETRIEVE_TS` -> `RETRIEVE_DECISIONS` -> `SYNTHESIZE_SCENARIOS`) so `TraceView.tsx` displays genuine multi-step agentic reasoning instead of a fixed 5-row pipeline.
  - **CRITICAL COORDINATION RULE**: Per `project_context.md` Sec. 5.6, `tests/integration/test_walking_skeleton.py` currently asserts `len(operator_results) == 5` and `step_count == 5`. Update those assertions intentionally in the same PR.

### Task 2C: Gate G3 Remaining L3 Verifier Rules
- **Lane**: `M2` (`src/asci/stages/stage_d_optimiser.py`) & `M1` (`src/asci/llm/explainer.py`)
- **Where the UI marks it pending**: `OverviewCommandView.tsx` -> `L1–L3 Math Checks` tab (`Gate G3 Pending Verifier Rules`)
- **What to add**:
  - `L3: LINE_STOP_SAFETY_THRESHOLD`: Flag/escalate when a critical assembly plant drops below safe cover margin despite unmet capacity remaining unused elsewhere.
  - `L3: PLAN_CHURN_LIMIT`: Compare flow allocation churn against the prior active plan for the same event to avoid erratic plan oscillations.
  - Strict claim-citation verification option (`strict_citation_gate=True`) that rejects/escalates uncited LLM numerical claims instead of only soft-stripping ungrounded `[CIT_...]` tags.

---

## 4. Priority 3 — Defer Until After Prototype Demo

Unless needed for final thesis evaluation, **do not block the prototype demo** on these Phase 6–9 items:
- **PyTorch Masked MLP Policy / DAgger Training (Gate G4)** (`Phase 6`) — rule-based budget controller already runs cleanly.
- **Full Benchmark Suites `S2 / S3 / S4 / S6`** (`Phase 7–8`, beyond `Suite S1` which already works in `scripts/run_suite_s1.py`).
- **Always-on Background Polling Cron Daemon** (`Phase 8`) — top-bar **`Poll Live Feeds`** + **`Auto 60s`** timer already handles live polling interactively for demos.
- **DuckDB / `faiss-cpu` / `sentence-transformers` swap** — NumPy + `HashedConceptBoW` + SQLite work deterministically with zero extra binary dependencies on Windows/Linux.

---

## 5. Non-Negotiable Coding & Architecture Rules

When modifying `asci-core/`, follow every invariant in `project_context.md` Sec. 5:
1. **Immutable `PipelineState`**: Never mutate `PipelineState` in place; always use `state.transition(updates=..., trace_item=...)`.
2. **Canonical Entity IDs Only**: Every node/entity must pass `CanonicalEntityRegistry.validate_id()`. Never invent hardcoded port/plant strings in routes or React components.
3. **Untrusted Text Isolation**: Any external headline/text entering Stage A or `SemanticVectorStore` must stay wrapped via `quote_untrusted_text()`.
4. **Honest Verifier Statuses**: Never stub L1–L3 verification checks to force `PASS`. If a plan fails verification, `PipelineStatus.FAILED` must surface to the UI.
5. **Secrets**: Keep API keys (e.g. `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) strictly in `.env` (gitignored); document new variables only in `.env.example`.

---

## 6. Local Dev Setup & Verification Commands

All commands run from `asci-core/`:

```bash
# 1. Environment variables (one-time)
cp .env.example .env
# Add GROQ_API_KEY=... (recommended free fast LLM) in .env

# 2. Backend lint + full test suite (must stay 100% green)
ruff check src tests scripts
pytest tests/ -q

# 3. Build React + TypeScript frontend into frontend/dist/
cd frontend
npm install
npm run build
cd ..

# 4. Run full-stack Control Tower with live data feeds + persistent SQLite
# PowerShell:
$env:PYTHONPATH = "src"
python scripts/run_demo.py --scale v1_corridor --preload --data-dir ./local_data --open

# macOS / Linux / Git Bash:
PYTHONPATH=src python scripts/run_demo.py --scale v1_corridor --preload --data-dir ./local_data --open
```

- **Frontend Hot-Reload Dev Mode** (while backend runs on `:8000`, Vite on `:5173` proxies API routes automatically via `frontend/vite.config.ts`):
  ```bash
  cd frontend && npm run dev
  ```
- **API Docs**: Open `http://127.0.0.1:8000/docs` for interactive Swagger testing of new endpoints (`/whatif`, `/outcomes`, `/evidence/{id}`, `/decisions`).

