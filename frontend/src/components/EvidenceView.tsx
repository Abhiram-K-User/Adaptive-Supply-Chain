import { useState } from "react";
import { BookOpen, FileSearch, Lock, Search } from "lucide-react";
import { asciApi } from "../api/client";
import type {
  DisruptionEventType,
  EvidenceProvenanceItem,
  TrustTier,
} from "../types/asci";

interface EvidenceViewProps {
  sessionEvidence: EvidenceProvenanceItem[];
}

export function EvidenceView({ sessionEvidence }: EvidenceViewProps) {
  const [query, setQuery] = useState("cyclone berth port diversion rail");
  const [entityId, setEntityId] = useState("");
  const [hazardType, setHazardType] = useState<DisruptionEventType | "">("");
  const [minTrustTier, setMinTrustTier] = useState<TrustTier | "">("");
  const [searchResults, setSearchResults] = useState<EvidenceProvenanceItem[] | null>(
    null
  );
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const items = await asciApi.searchEvidence({
        q: query.trim(),
        entity_id: entityId.trim() || undefined,
        hazard_type: hazardType,
        min_trust_tier: minTrustTier,
        limit: 9,
      });
      setSearchResults(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const displayedItems = searchResults ?? sessionEvidence;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <section className="rounded-xl border border-line bg-panel p-4 shadow-lg shadow-black/25">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-bold text-white">
                <BookOpen className="h-4 w-4 text-sky-400" />
                Evidence & Playbook Vector Memory (USKL)
              </h2>
              <p className="mt-0.5 text-xs text-slate-400">
                Live query against <code className="text-sky-300">GET /evidence/search</code> (HashedConceptBoW / FAISS + Trust Tier filtering)
              </p>
            </div>
            {searchResults !== null && (
              <button
                type="button"
                onClick={() => setSearchResults(null)}
                className="rounded-md border border-line bg-panel2 px-2.5 py-1 text-xs text-slate-300 hover:text-white"
              >
                Show Active Session Citations ({sessionEvidence.length})
              </button>
            )}
          </div>

          <form onSubmit={runSearch} className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-5">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Semantic search query..."
              className="sm:col-span-2 rounded-lg border border-line bg-[#090f1d] px-3 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />
            <input
              type="text"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="Entity ID (e.g. PORT_CHENNAI)"
              className="rounded-lg border border-line bg-[#090f1d] px-3 py-1.5 font-mono text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            />
            <select
              value={minTrustTier}
              onChange={(e) => setMinTrustTier(e.target.value as TrustTier | "")}
              className="rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            >
              <option value="">Any Trust Tier</option>
              <option value="TIER_A">Min TIER_A</option>
              <option value="TIER_B">Min TIER_B</option>
              <option value="TIER_C">Min TIER_C</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-sky-400 disabled:opacity-50"
            >
              <Search className="h-3.5 w-3.5" />
              {loading ? "Searching..." : "Search Corpus"}
            </button>
            <select
              value={hazardType}
              onChange={(e) =>
                setHazardType(e.target.value as DisruptionEventType | "")
              }
              className="sm:col-span-2 rounded-lg border border-line bg-[#090f1d] px-2.5 py-1.5 text-xs text-slate-100 focus:border-sky-400 focus:outline-none"
            >
              <option value="">All Hazard Types</option>
              <option value="HAZARD_PORT">HAZARD_PORT</option>
              <option value="HAZARD_ROAD">HAZARD_ROAD</option>
              <option value="PORT_CONGESTION_STRIKE">PORT_CONGESTION_STRIKE</option>
              <option value="RAIL_DISRUPTION">RAIL_DISRUPTION</option>
              <option value="SHIPPING_SCHEDULE">SHIPPING_SCHEDULE</option>
              <option value="TRADE_POLICY">TRADE_POLICY</option>
              <option value="PLANT_OUTAGE">PLANT_OUTAGE</option>
            </select>
          </form>

          {error && (
            <div className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}
        </section>

        <div className="space-y-2.5">
          {displayedItems.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line bg-panel p-8 text-center text-xs text-slate-400">
              No evidence records available yet. Run a plan in Command Center or click
              "Search Corpus" above.
            </div>
          ) : (
            displayedItems.map((doc) => (
              <div
                key={doc.citation_id}
                onClick={() => setSelectedCitationId(doc.citation_id)}
                className={`cursor-pointer rounded-xl border bg-panel p-4 transition ${
                  selectedCitationId === doc.citation_id
                    ? "border-sky-400"
                    : "border-line hover:border-sky-400/50"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-sky-300">
                      [{doc.citation_id}]
                    </span>
                    <span className="text-xs text-slate-400">{doc.source}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {doc.publication_date && (
                      <span className="text-[11px] text-slate-400">
                        Published: {doc.publication_date}
                      </span>
                    )}
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        doc.trust_tier === "TIER_A"
                          ? "bg-emerald-500/15 text-emerald-300"
                          : doc.trust_tier === "TIER_B"
                          ? "bg-sky-500/15 text-sky-300"
                          : "bg-red-500/15 text-red-300"
                      }`}
                    >
                      {doc.trust_tier}
                    </span>
                  </div>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-200">
                  {doc.snippet}
                </p>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {doc.entity_ids.map((eid) => (
                    <span
                      key={eid}
                      className="rounded border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px] text-slate-300"
                    >
                      {eid}
                    </span>
                  ))}
                  {doc.supported_claims.map((claim) => (
                    <span
                      key={claim}
                      className="rounded border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-200"
                    >
                      Claim: {claim}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Planned Single Evidence Endpoint Placeholder */}
      <aside className="space-y-3">
        <div className="rounded-xl border border-dashed border-amber-500/50 bg-panel p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-300">
              <FileSearch className="h-4 w-4" />
              Single Citation Drill-Down
            </h3>
            <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-300">
              Placeholder
            </span>
          </div>

          <p className="mt-2 text-xs leading-relaxed text-slate-300">
            Selected ID:{" "}
            <span className="font-mono text-sky-300">
              {selectedCitationId ?? "Click an evidence card on the left"}
            </span>
          </p>

          <div className="mt-3 rounded-lg border border-line bg-[#0a1122] p-3 text-xs text-slate-400">
            <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-slate-200">
              <Lock className="h-3.5 w-3.5 text-amber-400" />
              GET /evidence/{"{id}"} — Planned (PRD 10.2 / M3)
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed">
              Per <code className="text-slate-300">project_context.md</code> Sec. 7, direct
              single-citation retrieval (<code className="text-slate-300">GET /evidence/&#123;id&#125;</code>)
              with full document provenance, time-series recovery curve attachments, and claim-level
              verifiability hashes is queued under Team Lane M3.
            </p>
          </div>
        </div>
      </aside>
    </div>
  );
}

