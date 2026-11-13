import type {
  CanonicalEntity,
  DecisionRecord,
  DisruptionEvent,
  DisruptionEventType,
  EvidenceDetail,
  EvidenceProvenanceItem,
  FeedsStatusResponse,
  HealthResponse,
  IngestEventPayload,
  LLMStatusResponse,
  MitigateEventPayload,
  MitigateEventResponse,
  NetworkSummaryResponse,
  OperatorTraceEntry,
  PlanResponse,
  GeneratePlanPayload,
  RealizedOutcomePayload,
  RealizedOutcomeResponse,
  RecordDecisionPayload,
  RecordDecisionResponse,
  ReplayIngestResponse,
  TrustTier,
  WhatIfRequest,
  WhatIfResponse,
} from "../types/asci";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const rawText = await res.text();
      try {
        const parsed = JSON.parse(rawText) as {
          detail?: unknown;
          message?: unknown;
          error?: unknown;
        };
        const msg = parsed?.detail ?? parsed?.message ?? parsed?.error;
        if (msg) {
          detail = typeof msg === "string" ? msg : JSON.stringify(msg);
        } else if (rawText.trim()) {
          detail = rawText.trim();
        }
      } catch {
        if (rawText.trim()) {
          detail = rawText.trim();
        }
      }
    } catch {
      // Body stream could not be read; fallback to status code
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const asciApi = {
  getHealth: () => requestJson<HealthResponse>("/health"),

  getLlmStatus: (provider?: string) =>
    requestJson<LLMStatusResponse>(
      provider && provider !== "auto"
        ? `/llm/status?provider=${encodeURIComponent(provider)}`
        : "/llm/status"
    ),

  getRegistry: () => requestJson<CanonicalEntity[]>("/registry"),

  getNetwork: () => requestJson<NetworkSummaryResponse>("/network"),

  listEvents: () => requestJson<DisruptionEvent[]>("/events"),

  ingestEvent: (payload: IngestEventPayload) =>
    requestJson<DisruptionEvent>("/events", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  pollReplayFeeds: (useFallback = true) =>
    requestJson<ReplayIngestResponse>(`/ingest/replay?use_fallback=${useFallback}`, {
      method: "POST",
    }),

  pollLiveFeeds: () =>
    requestJson<ReplayIngestResponse>("/ingest/live", {
      method: "POST",
    }),

  getFeedsStatus: () => requestJson<FeedsStatusResponse>("/feeds/status"),

  generatePlan: (eventId: string, payload: GeneratePlanPayload) =>
    requestJson<PlanResponse>(`/events/${encodeURIComponent(eventId)}/plan`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  mitigateEvent: (eventId: string, payload: MitigateEventPayload = {}) =>
    requestJson<MitigateEventResponse>(`/events/${encodeURIComponent(eventId)}/mitigate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  reopenEvent: (eventId: string) =>
    requestJson<DisruptionEvent>(`/events/${encodeURIComponent(eventId)}/reopen`, {
      method: "POST",
    }),

  recordDecision: (payload: RecordDecisionPayload) =>
    requestJson<RecordDecisionResponse>("/decisions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  searchEvidence: (params: {
    q: string;
    entity_id?: string;
    region?: string;
    hazard_type?: DisruptionEventType | "";
    min_trust_tier?: TrustTier | "";
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    qs.set("q", params.q);
    if (params.entity_id) qs.set("entity_id", params.entity_id);
    if (params.region) qs.set("region", params.region);
    if (params.hazard_type) qs.set("hazard_type", params.hazard_type);
    if (params.min_trust_tier) qs.set("min_trust_tier", params.min_trust_tier);
    qs.set("limit", String(params.limit ?? 8));
    return requestJson<EvidenceProvenanceItem[]>(`/evidence/search?${qs.toString()}`);
  },

  getSessionTraces: (sessionId: string) =>
    requestJson<OperatorTraceEntry[]>(`/traces/${encodeURIComponent(sessionId)}`),

  listDecisions: (planId?: string, limit = 20) => {
    const qs = new URLSearchParams();
    if (planId) qs.set("plan_id", planId);
    qs.set("limit", String(limit));
    return requestJson<DecisionRecord[]>(`/decisions?${qs.toString()}`);
  },

  getEvidenceDetail: (citationId: string) =>
    requestJson<EvidenceDetail>(`/evidence/${encodeURIComponent(citationId)}`),

  recordOutcome: (payload: RealizedOutcomePayload) => {
    const qs = new URLSearchParams();
    qs.set("entity_id", payload.entity_id);
    qs.set("hazard_type", payload.hazard_type);
    qs.set("day_offset", String(payload.day_offset));
    qs.set("observed_teu", String(payload.observed_teu));
    if (payload.vessel_calls !== undefined) qs.set("vessel_calls", String(payload.vessel_calls));
    if (payload.obs_date) qs.set("obs_date", payload.obs_date);
    return requestJson<RealizedOutcomeResponse>(`/outcomes?${qs.toString()}`, {
      method: "POST",
    });
  },

  getOutcomesForEntity: (entityId: string, windowDays = 30) =>
    requestJson<Record<string, unknown>>(
      `/outcomes/${encodeURIComponent(entityId)}?window_days=${windowDays}`
    ),

  runWhatIf: (payload: WhatIfRequest) =>
    requestJson<WhatIfResponse>("/whatif", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

