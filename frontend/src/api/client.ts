import type {
  CanonicalEntity,
  DisruptionEvent,
  DisruptionEventType,
  EvidenceProvenanceItem,
  FeedsStatusResponse,
  HealthResponse,
  IngestEventPayload,
  LLMStatusResponse,
  NetworkSummaryResponse,
  OperatorTraceEntry,
  PlanResponse,
  GeneratePlanPayload,
  RecordDecisionPayload,
  RecordDecisionResponse,
  ReplayIngestResponse,
  TrustTier,
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
};

