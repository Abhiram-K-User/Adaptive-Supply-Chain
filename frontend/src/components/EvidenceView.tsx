import { useState } from "react";
import { BookOpen, Search, ShieldCheck, TrendingUp, Calendar, Hash } from "lucide-react";
import { asciApi } from "../api/client";
import type {
  DisruptionEventType,
  EvidenceDetail,
  EvidenceProvenanceItem,
  TrustTier,
} from "../types/asci";

interface EvidenceViewProps {
  sessionEvidence: EvidenceProvenanceItem[];
}

export function EvidenceView({ sessionEvidence }: EvidenceViewProps) {
  const [query, setQuery] = useState("cyclone berth port diversion rail");
  const [entityId, setEntityId] = useState("");
  const [hazardType] = useState<DisruptionEventType | "">("");
  const [minTrustTier, setMinTrustTier] = useState<TrustTier | "">("");
  const [searchResults, setSearchResults] = useState<EvidenceProvenanceItem[] | null>(
    null
  );
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [evidenceDetail, setEvidenceDetail] = useState<EvidenceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelectCitation = (id: string) => {
    setSelectedCitationId(id);
    setDetailLoading(true);
    asciApi
      .getEvidenceDetail(id)
      .then((detail) => setEvidenceDetail(detail))
      .catch(() => setEvidenceDetail(null))
      .finally(() => setDetailLoading(false));
  };

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
        <section className="rounded-2xl border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-bold text-light-text-primary dark:text-dark-text-primary">
                <BookOpen className="h-4 w-4 text-teal-600 dark:text-accent-cyan" />
                Evidence &amp; SOP Playbook Vector Memory (USKL)
              </h2>
              <p className="mt-0.5 text-xs text-light-text-secondary dark:text-dark-text-secondary">
                Semantic vector lookup against <code className="font-mono text-teal-600 dark:text-accent-cyan">GET /evidence/search</code> (HashedConceptBoW / FAISS + Trust Tier filtering)
              </p>
            </div>
            {searchResults !== null && (
              <button
                type="button"
                onClick={() => setSearchResults(null)}
                className="rounded-lg border border-light-border bg-light-surface-subtle px-2.5 py-1 text-xs text-light-text-secondary hover:text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary dark:hover:text-dark-text-primary"
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
              className="sm:col-span-2 rounded-lg border border-light-border bg-light-surface-subtle px-3 py-1.5 text-xs text-light-text-primary focus:border-teal-500 focus:bg-white focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:focus:border-accent-cyan"
            />
            <input
              type="text"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="Entity ID (e.g. PORT_CHENNAI)"
              className="rounded-lg border border-light-border bg-light-surface-subtle px-3 py-1.5 font-mono text-xs text-light-text-primary focus:border-teal-500 focus:bg-white focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary dark:focus:border-accent-cyan"
            />
            <select
              value={minTrustTier}
              onChange={(e) => setMinTrustTier(e.target.value as TrustTier | "")}
              className="rounded-lg border border-light-border bg-light-surface-subtle px-2.5 py-1.5 text-xs text-light-text-primary focus:border-teal-500 focus:outline-none dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
            >
              <option value="">Any Trust Tier</option>
              <option value="TIER_A">Min TIER_A</option>
              <option value="TIER_B">Min TIER_B</option>
              <option value="TIER_C">Min TIER_C</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#101C2C] px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50 transition dark:bg-accent-cyan dark:text-[#090D14] dark:hover:bg-cyan-400"
            >
              <Search className="h-3.5 w-3.5" />
              <span>{loading ? "Searching..." : "Vector Query"}</span>
            </button>
          </form>

          {error && (
            <div className="mt-2 rounded-lg border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-300">
              {error}
            </div>
          )}
        </section>

        {/* Results List */}
        <section className="space-y-2">
          <div className="flex items-center justify-between text-xs text-light-text-muted dark:text-dark-text-muted">
            <span>
              {searchResults ? "Query Results" : "Active Session Grounding Evidence"}{" "}
              ({displayedItems.length})
            </span>
            <span className="font-mono text-[10px]">
              Vector Index: 9 SOP playbooks + live signals
            </span>
          </div>

          {displayedItems.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-light-border bg-white p-8 text-center text-xs text-light-text-muted dark:border-dark-border dark:bg-dark-card dark:text-dark-text-muted">
              No evidence documents match query. Try searching &quot;cyclone&quot;, &quot;rail&quot;, or &quot;port&quot;.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-2.5">
              {displayedItems.map((item) => {
                const isSelected = selectedCitationId === item.citation_id;
                const isTierA = item.trust_tier === "TIER_A";
                const isTierB = item.trust_tier === "TIER_B";
                return (
                  <div
                    key={item.citation_id}
                    onClick={() => handleSelectCitation(item.citation_id)}
                    className={`cursor-pointer rounded-2xl border p-3.5 transition ${
                      isSelected
                        ? "border-google-blue bg-blue-50/40 shadow-xs dark:border-google-blue dark:bg-blue-950/20"
                        : "border-light-border bg-white hover:border-slate-300 dark:border-dark-border dark:bg-dark-card dark:hover:border-dark-hover"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-light-text-primary dark:text-dark-text-primary">
                          [{item.citation_id}]
                        </span>
                        <span className="text-xs font-semibold text-light-text-secondary dark:text-dark-text-secondary">
                          {item.source}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                            isTierA
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400"
                              : isTierB
                              ? "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-400"
                              : "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-400"
                          }`}
                        >
                          {item.trust_tier}
                        </span>
                        {item.relevance_score !== undefined && (
                          <span className="font-mono text-[10px] text-light-text-muted dark:text-dark-text-muted">
                            Score: {item.relevance_score.toFixed(2)}
                          </span>
                        )}
                      </div>
                    </div>

                    <p className="mt-2 text-xs text-light-text-secondary leading-relaxed dark:text-dark-text-secondary">
                      &quot;{item.snippet}&quot;
                    </p>

                    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                      {item.entity_ids.map((id) => (
                        <span
                          key={id}
                          className="rounded bg-light-surface-subtle px-1.5 py-0.5 font-mono text-light-text-secondary dark:bg-dark-surface dark:text-dark-text-secondary"
                        >
                          {id}
                        </span>
                      ))}
                      {item.supported_claims.map((claim, ci) => (
                        <span
                          key={ci}
                          className="rounded bg-teal-50 px-1.5 py-0.5 font-medium text-teal-800 dark:bg-teal-950/50 dark:text-teal-300"
                        >
                          {claim}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Right Column: Citation Inspector */}
      <aside className="rounded-2xl border border-light-border bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-card dark:shadow-dark-card space-y-3">
        <div className="flex items-center justify-between border-b border-light-border dark:border-dark-border pb-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-light-text-primary dark:text-dark-text-primary">
            Citation Detail Inspector
          </h3>
          <span className="font-mono text-[9px] text-google-blue bg-blue-50 dark:bg-blue-950/40 px-1.5 py-0.5 rounded">
            GET /evidence/:id
          </span>
        </div>

        {selectedCitationId ? (
          (() => {
            const current = displayedItems.find(
              (i) => i.citation_id === selectedCitationId
            );
            if (!current) return null;
            const detail = evidenceDetail;
            const recoveryCurves = detail?.recovery_curves ?? {};
            const curveKeys = Object.keys(recoveryCurves);

            return (
              <div className="space-y-3 text-xs">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-google-blue">
                      [{current.citation_id}]
                    </span>
                    <span className="rounded bg-light-secondary dark:bg-dark-elevated px-1.5 py-0.5 text-[10px] font-semibold text-light-text-secondary dark:text-dark-text-secondary">
                      {detail?.trust_tier ?? current.trust_tier}
                    </span>
                  </div>
                  <div className="font-semibold text-light-text-primary dark:text-dark-text-primary mt-1">
                    {current.source}
                  </div>
                  {detail?.publication_date && (
                    <div className="flex items-center gap-1 text-[10px] text-light-text-muted dark:text-dark-text-muted mt-0.5">
                      <Calendar className="h-3 w-3" />
                      <span>Published: {detail.publication_date}</span>
                      {detail.expires_at && <span>· Expires: {detail.expires_at}</span>}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-light-border bg-light-secondary/60 p-2.5 text-[11px] text-light-text-secondary leading-relaxed dark:border-dark-border dark:bg-dark-elevated/60 dark:text-dark-text-secondary">
                  {current.snippet}
                </div>

                {/* Grounded Target Entities */}
                <div>
                  <div className="font-semibold text-light-text-primary dark:text-dark-text-primary mb-1">
                    Grounded Target Entities
                  </div>
                  <div className="flex flex-wrap gap-1 font-mono text-[10px]">
                    {current.entity_ids.map((id) => (
                      <span
                        key={id}
                        className="rounded border border-light-border bg-light-surface px-2 py-0.5 text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-primary"
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Linked Port Recovery Curves */}
                {curveKeys.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1 font-semibold text-light-text-primary dark:text-dark-text-primary mb-1.5">
                      <TrendingUp className="h-3.5 w-3.5 text-google-green" />
                      <span>Port Recovery Curve (TimeSeriesStore)</span>
                    </div>
                    {curveKeys.map((key) => {
                      const points = recoveryCurves[key] as number[];
                      return (
                        <div key={key} className="space-y-1.5 rounded-lg border border-light-border dark:border-dark-border bg-light-secondary/40 dark:bg-dark-elevated/40 p-2">
                          <div className="font-mono text-[10px] text-google-blue font-semibold">
                            {key}
                          </div>
                          <div className="space-y-1">
                            {points.map((mult, idx) => {
                              const pct = Math.round(mult * 100);
                              return (
                                <div key={idx} className="flex items-center gap-2 text-[10px]">
                                  <span className="w-10 text-light-text-muted dark:text-dark-text-muted shrink-0">
                                    Day +{idx + 1}:
                                  </span>
                                  <div className="flex-1 bg-light-border dark:bg-dark-border h-2 rounded-full overflow-hidden">
                                    <div
                                      className="bg-google-green h-full rounded-full transition-all"
                                      style={{ width: `${Math.min(100, pct)}%` }}
                                    />
                                  </div>
                                  <span className="w-8 text-right font-mono font-bold text-light-text-primary dark:text-dark-text-primary shrink-0">
                                    {pct}%
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Supported Mitigation Claims */}
                <div>
                  <div className="font-semibold text-light-text-primary dark:text-dark-text-primary mb-1">
                    Supported Mitigation Claims
                  </div>
                  <ul className="space-y-1 text-[11px] text-light-text-secondary dark:text-dark-text-secondary">
                    {current.supported_claims.map((cl, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5 text-google-blue mt-0.5 shrink-0" />
                        <span>{cl}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })()
        ) : (
          <div className="py-8 text-center text-xs text-light-text-muted dark:text-dark-text-muted">
            Select any citation card to inspect detailed grounded claims, metadata, and port recovery trajectories.
          </div>
        )}
      </aside>
    </div>
  );
}
