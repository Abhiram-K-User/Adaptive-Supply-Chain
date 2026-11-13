export type TrustTier = "TIER_A" | "TIER_B" | "TIER_C";

export type DisruptionEventType =
  | "HAZARD_PORT"
  | "HAZARD_ROAD"
  | "PORT_CONGESTION_STRIKE"
  | "RAIL_DISRUPTION"
  | "SHIPPING_SCHEDULE"
  | "TRADE_POLICY"
  | "PLANT_OUTAGE";

export type EventStatus = "NEW" | "UPDATED" | "MITIGATED" | "RETRACTED" | "EXPIRED";

export type RiskMode = "CVAR" | "EXPECTED_COST" | "DETERMINISTIC";

export type SolverType = "OR_TOOLS" | "NETWORKX";

export type ControllerMode =
  | "rule_router"
  | "learned_mlp"
  | "always_full"
  | "fixed_rag"
  | "no_rag";

export type LLMProvider =
  | "auto"
  | "groq"
  | "gemini"
  | "openai"
  | "ollama"
  | "deterministic";

export type PipelineStatus =
  | "INITIALIZED"
  | "PERCEIVED"
  | "ANALYZED"
  | "PLANNED"
  | "VERIFIED"
  | "COMPLETED"
  | "ESCALATED"
  | "FAILED";

export interface HealthResponse {
  status: string;
  corridor: string;
  version: string;
  network_scale: "v0_core" | "v1_corridor" | string;
  persistence: "sqlite_file" | "in_memory" | string;
}

export interface LLMStatusResponse {
  configured: boolean;
  active_provider: string;
  model: string;
  mode: "live_llm" | "deterministic_offline" | string;
  endpoint: string | null;
  supported_providers: string[];
}

export interface CanonicalEntity {
  id: string;
  name: string;
  entity_type: "PORT" | "PLANT" | "ICD" | "CFS" | "CORRIDOR_JUNCTION" | string;
  region: string;
  latitude: number;
  longitude: number;
  aliases?: string[];
  daily_capacity_teu?: number | null;
  daily_demand_teu?: number | null;
  days_of_cover?: number | null;
}

export interface NetworkEdgeSummary {
  id: string;
  source: string;
  target: string;
  mode: "ROAD" | "RAIL" | "INTERMODAL_RAIL" | string;
  distance_km: number;
}

export interface NetworkSummaryResponse {
  node_count: number;
  edge_count: number;
  nodes: string[];
  edges: NetworkEdgeSummary[];
}

export interface DisruptionEvent {
  event_id: string;
  event_type: DisruptionEventType;
  status: EventStatus;
  primary_entity_id: string;
  affected_entity_ids: string[];
  severity: number;
  estimated_duration_days: number;
  source_feed: string;
  raw_headline: string;
  raw_text: string;
  timestamp: string;
  corroboration_count: number;
  confidence: number;
  applied_plan_id?: string | null;
  mitigated_at?: string | null;
}

export interface IngestEventPayload {
  raw_headline: string;
  raw_text: string;
  source_feed?: string;
  trust_tier: TrustTier;
  primary_entity_id?: string | null;
  affected_entity_ids?: string[];
  event_type?: DisruptionEventType | null;
  severity?: number | null;
  estimated_duration_days?: number | null;
  enable_llm: boolean;
  llm_provider?: LLMProvider | null;
}

export interface FeedSourceStatus {
  source: string;
  fetch_mode: string;
  signals_fetched: number;
  corridor_events_grounded: number;
  fetched_at: string | null;
  error: string | null;
}

export interface WeatherTelemetryRow {
  entity_id: string;
  name: string;
  region: string;
  obs_date: string;
  rain_mm: number;
  wind_kmh: number;
  weather_code: number;
  alert_color: "GREEN" | "YELLOW" | "ORANGE" | "RED" | string;
}

export interface FeedsStatusResponse {
  live_feeds_enabled: boolean;
  poll_interval_seconds: number;
  last_polled_at: string | null;
  last_mode: string;
  source_statuses: FeedSourceStatus[];
  weather_telemetry: WeatherTelemetryRow[];
}

export interface ReplayIngestResponse {
  signals_collected: number;
  events_persisted: number;
  mode?: string;
  source_statuses?: FeedSourceStatus[];
  weather_telemetry?: WeatherTelemetryRow[];
  events: Array<{
    event_id: string;
    primary_entity_id: string;
    affected_entity_ids: string[];
    event_type: DisruptionEventType;
    severity: number;
    confidence: number;
    corroboration_count: number;
    status: EventStatus;
  }>;
}

export interface GeneratePlanPayload {
  lambda_cost_budget?: number;
  random_seed?: number;
  k_hop_neighborhood?: number;
  risk_mode: RiskMode;
  cvar_alpha?: number;
  solver_type?: SolverType;
  controller_mode?: ControllerMode;
  propagation_tier: 1 | 2;
  enable_llm: boolean;
  llm_provider?: LLMProvider | null;
}

export interface FlowAllocation {
  commodity: string;
  origin_id: string;
  destination_id: string;
  path: string[];
  mode: string;
  flow_teu: number;
  unit_cost: number;
  total_cost: number;
}

export interface MitigationPlan {
  plan_id: string;
  timestamp: string;
  objective_cost: number;
  allocations: FlowAllocation[];
  unmet_demand_teu: number;
  mode_split: Record<string, number>;
  risk_mode: string;
  cvar_cost: number | null;
  solver_engine: string;
  summary: string;
}

export interface VerificationCheck {
  layer: "L1" | "L2" | "L3" | string;
  check_name: string;
  verdict: "PASS" | "FAIL" | "WARN";
  details: string;
  metrics: Record<string, unknown>;
}

export interface VerificationReport {
  overall_verdict: "PASS" | "FAIL" | "WARN";
  passed: boolean;
  l1_checks: VerificationCheck[];
  l2_checks: VerificationCheck[];
  l3_checks: VerificationCheck[];
  failed_checks: string[];
}

export interface CytoscapeNode {
  data: {
    id: string;
    label: string;
    entity_type: string;
    lat: number;
    lon: number;
    region: string;
    capacity_multiplier: number;
    status: "NORMAL" | "RESTRICTED" | "DISRUPTED" | string;
  };
}

export interface CytoscapeEdge {
  data: {
    id: string;
    source: string;
    target: string;
    mode: string;
    distance_km: number;
    capacity_multiplier: number;
    freight_flow_teu: number;
  };
}

export interface LineStopForecastRow {
  plant_id: string;
  plant_name: string;
  days_of_cover: number;
  expected_delay_days: number;
  time_to_line_stop_days: number;
  line_stop_risk: number;
  critical: boolean;
}

export interface EvidenceProvenanceItem {
  citation_id: string;
  source: string;
  trust_tier: TrustTier;
  entity_ids: string[];
  snippet: string;
  supported_claims: string[];
  publication_date?: string;
  relevance_score?: number;
  region?: string | null;
  hazard_types?: DisruptionEventType[];
  expires_at?: string | null;
}

export interface ExecutiveBriefing {
  mode: "live_llm" | "deterministic_grounded" | string;
  provider: string;
  model: string;
  headline: string;
  executive_summary: string;
  key_actions: string[];
  line_stop_watchouts: string[];
  cited_ids: string[];
  rejected_citations: string[];
  citation_verified: boolean;
  fallback_reason?: string | null;
}

export interface OperatorTraceEntry {
  step_index: number;
  operator_type: string;
  input_summary: string;
  output_summary: string;
  duration_ms: number;
  cost: number;
  seed: number;
  timestamp: string;
}

export interface DashboardPayload {
  event_summary: {
    event_id?: string;
    event_type?: DisruptionEventType;
    primary_entity_id?: string;
    severity?: number;
    confidence?: number;
    headline?: string;
    source_feed?: string;
    duration_days?: number;
  };
  geospatial_network: {
    nodes: CytoscapeNode[];
    edges: CytoscapeEdge[];
  };
  line_stop_forecast: LineStopForecastRow[];
  evidence_provenance: EvidenceProvenanceItem[];
  mitigation_summary: {
    plan_id?: string;
    objective_cost?: number;
    unmet_demand_teu?: number;
    mode_split?: Record<string, number>;
    summary?: string;
    verification_passed?: boolean;
    allocations?: FlowAllocation[];
  };
  trace_timeline: OperatorTraceEntry[];
  executive_briefing: ExecutiveBriefing;
}

export interface PlanResponse {
  session_id: string;
  event_id: string;
  status: PipelineStatus;
  plan: MitigationPlan | null;
  verification: VerificationReport | null;
  dashboard: DashboardPayload | null;
  compute_cost: number;
  step_count: number;
}

export interface RecordDecisionPayload {
  plan_id: string;
  session_id: string;
  decision: "APPROVE" | "EDIT" | "REJECT";
  planner_id: string;
  comments: string;
  modifications?: Record<string, unknown>;
}

export interface RecordDecisionResponse {
  decision_id: number;
  plan_id: string;
  session_id: string;
  decision: string;
  planner_id: string;
  indexed_citation_id?: string | null;
  event_status?: string | null;
}

export interface MitigateEventPayload {
  plan_id?: string | null;
  session_id?: string | null;
  planner_id?: string;
  comments?: string;
}

export interface MitigateEventResponse {
  event: DisruptionEvent;
  plan_id?: string | null;
  decision_id?: number | null;
  indexed_citation_id?: string | null;
}

export interface DecisionRecord {
  decision_id: number;
  plan_id: string;
  session_id: string;
  decision: "APPROVE" | "EDIT" | "REJECT";
  planner_id: string;
  comments: string;
  modifications_json: string;
  timestamp: string;
}

export interface WhatIfRequest {
  event_id?: string | null;
  target_entity_id: string;
  capacity_multiplier: number;
  duration_days: number;
  risk_mode: "DETERMINISTIC" | "EXPECTED_COST" | "CVAR";
  propagation_tier: 1 | 2;
  baseline_plan_id?: string | null;
}

export interface WhatIfResponse {
  simulated_plan: MitigationPlan | null;
  verification: VerificationReport | null;
  cost_delta: number;
  unmet_demand_delta_teu: number;
  rail_share_delta_pct: number;
  baseline_total_cost: number;
  simulated_total_cost: number;
}

export interface EvidenceDetail {
  citation_id: string;
  source: string;
  trust_tier: TrustTier;
  entity_ids: string[];
  snippet: string;
  publication_date: string;
  supported_claims: string[];
  region?: string | null;
  hazard_types?: DisruptionEventType[];
  expires_at?: string | null;
  untrusted_quoted?: boolean;
  relevance_score?: number;
  recovery_curves?: Record<string, number[]>;
}

export interface RealizedOutcomePayload {
  entity_id: string;
  hazard_type: string;
  day_offset: number;
  observed_teu: number;
  vessel_calls?: number;
  obs_date?: string;
}

export interface RealizedOutcomeResponse {
  entity_id: string;
  hazard_type: string;
  day_offset: number;
  observed_teu: number;
  baseline_teu: number;
  realized_multiplier: number;
  deviation_pct: number;
  updated_recovery_curve: number[];
}

export type ActiveWorkspaceTab =
  | "overview"
  | "network"
  | "inventory"
  | "forecasting"
  | "suppliers"
  | "risk"
  | "optimization"
  | "analytics"
  // Legacy aliases for internal deep linking
  | "command"
  | "evidence"
  | "trace"
  | "whatif"
  | "outcomes";

