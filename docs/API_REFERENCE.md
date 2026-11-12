# ASCI REST API Reference

> **Adaptive Supply Chain Intelligence (ASCI) Platform**  
> REST API Specification (FastAPI / OpenAPI 3.1)

---

## 1. System Endpoints

### 1.1. Health Check
- **Route**: `GET /health`
- **Description**: Returns overall system operational status, active entity counts, edge counts, and persistent store status.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "active_nodes": 118,
  "active_edges": 364,
  "events_persisted": 4,
  "uptime_seconds": 128.4
}
```

### 1.2. LLM Status
- **Route**: `GET /llm/status`
- **Query Parameters**:
  - `provider` (optional): `auto | groq | gemini | openai | ollama | deterministic`
- **Response `200 OK`**:
```json
{
  "active_provider": "groq",
  "model_name": "llama-3.3-70b-versatile",
  "is_fallback": false,
  "healthy": true
}
```

---

## 2. Registry & Network Endpoints

### 2.1. Canonical Entity Registry
- **Route**: `GET /registry`
- **Description**: Retrieves all validated nodes in the active corridor topology.
- **Response `200 OK`**:
```json
[
  {
    "id": "PORT_CHENNAI",
    "canonical_name": "Chennai Port (Madras Port)",
    "entity_type": "PORT",
    "state": "Tamil Nadu",
    "latitude": 13.0844,
    "longitude": 80.2928,
    "daily_capacity_teu": 5000.0,
    "aliases": ["Madras Port", "Chennai Sea Port"]
  }
]
```

### 2.2. Network Topology & Flows
- **Route**: `GET /network`
- **Description**: Returns all directed edges, transport modes, capacities, and base transit times.
- **Response `200 OK`**:
```json
{
  "scale": "v1_corridor",
  "node_count": 118,
  "edge_count": 364,
  "edges": [
    {
      "source": "PORT_CHENNAI",
      "target": "PLANT_HYUNDAI_SRIPERUMBUDUR",
      "mode": "ROAD",
      "distance_km": 48.5,
      "base_transit_hours": 2.5,
      "capacity_teu_per_day": 1200.0
    }
  ]
}
```

---

## 3. Disruption Events & Ingestion

### 3.1. Submit Disruption Event
- **Route**: `POST /events`
- **Status Code**: `201 Created`
- **Request Body**:
```json
{
  "raw_headline": "Severe Cyclone Warning Issued for Ennore Coastal Hub",
  "raw_text": "Port operations at Kamarajar Port (Ennore) are suspended for 72 hours due to heavy coastal winds.",
  "source_feed": "IMD_WEATHER_BULLETIN",
  "trust_tier": "TIER_A",
  "enable_llm": false
}
```
- **Response `201 Created`**:
```json
{
  "event_id": "evt_4a71b2d9e03f",
  "primary_entity_id": "PORT_KAMARAJAR",
  "affected_entity_ids": ["PORT_KAMARAJAR", "CORR_NH16_ENNORE"],
  "event_type": "WEATHER_EVENT",
  "severity": 0.85,
  "confidence": 0.95,
  "corroboration_count": 1,
  "status": "NEW"
}
```

### 3.2. List Events
- **Route**: `GET /events`
- **Response `200 OK`**: Array of active `DisruptionEvent` objects.

### 3.3. Replay Historical Feeds
- **Route**: `POST /ingest/replay`
- **Description**: Replays curated historical disaster signals through Stage A perception.

### 3.4. Trigger Live Feed Ingestion
- **Route**: `POST /ingest/live`
- **Description**: Polls live external feeds (GDACS, GDELT, IMD Weather, IMF PortWatch).

### 3.5. Feeds Telemetry Status
- **Route**: `GET /feeds/status`
- **Description**: Returns polling status and weather telemetry across South India logistics hubs.

---

## 4. Planning & Optimization

### 4.1. Run 5-Stage Optimization Plan
- **Route**: `POST /events/{event_id}/plan`
- **Request Body**:
```json
{
  "risk_mode": "CVAR",
  "cvar_alpha": 0.95,
  "max_cost_budget": 1000000.0,
  "step_limit": 5,
  "strict_citation_gate": true
}
```
- **Response `200 OK`**:
```json
{
  "session_id": "sess_f83910c4a",
  "event_id": "evt_4a71b2d9e03f",
  "status": "COMPLETED",
  "plan": {
    "plan_id": "plan_7b8a9c2d1e",
    "total_cost": 412500.0,
    "flow_allocations": [
      {
        "source": "PORT_KATTUPALLI",
        "target": "PLANT_HYUNDAI_SRIPERUMBUDUR",
        "commodity": "POWERTRAIN_CKD",
        "allocated_teu": 450.0,
        "mode": "ROAD"
      }
    ]
  },
  "verification": {
    "status": "PASS",
    "dual_solver_gap": 0.0003,
    "checks": [
      {"name": "L1:CONSERVATION_OF_FLOW", "status": "PASS"},
      {"name": "L1:CAPACITY_BOUNDS", "status": "PASS"},
      {"name": "L2:DUAL_SOLVER_AGREEMENT", "status": "PASS"},
      {"name": "L2:PER_COMMODITY_DEMAND", "status": "PASS"}
    ]
  },
  "compute_cost": 0.042,
  "step_count": 5
}
```

### 4.2. Retrieve Persisted Plan
- **Route**: `GET /plans/{plan_id}`
- **Response `200 OK`**: Serialized `MitigationPlan` object.

### 4.3. Record Human Operator Decision (Loop L2)
- **Route**: `POST /decisions`
- **Status Code**: `201 Created`
- **Request Body**:
```json
{
  "plan_id": "plan_7b8a9c2d1e",
  "session_id": "sess_f83910c4a",
  "decision": "APPROVE",
  "planner_id": "OP_SR_LOGISTICS_CHENNAI",
  "comments": "Approved diversion via Kattupalli and Krishnapatnam ports."
}
```
- **Response `201 Created`**:
```json
{
  "decision_id": "dec_89ef1203",
  "plan_id": "plan_7b8a9c2d1e",
  "session_id": "sess_f83910c4a",
  "decision": "APPROVE",
  "planner_id": "OP_SR_LOGISTICS_CHENNAI"
}
```

### 4.4. Operator Traces
- **Route**: `GET /traces/{session_id}`
- **Description**: Returns chronological operator traces detailing each step in the pipeline.

---

## 5. USKL Knowledge Endpoints

### 5.1. Semantic Vector Search
- **Route**: `GET /evidence/search`
- **Query Parameters**:
  - `query` (string, required): Search query (e.g., "cyclone port diversion protocol")
  - `limit` (integer, default 5): Maximum items
  - `region` (optional): Filter by state
- **Response `200 OK`**: Ranked list of matching SOP playbook fragments with citation identifiers.

