import { useEffect, useState } from "react";
import { asciApi, type Phase8Evaluation } from "../api/client";

const titles: Record<number, string> = {
  1: "Graph analysis", 2: "Retrieval value", 3: "Retrieval modalities",
  4: "Explanation grounding", 5: "Sufficiency gate", 6: "Adaptive control",
  7: "Propagation engines", 8: "Scenario planning and CVaR", 9: "Historical PortWatch alignment",
};
const descriptions: Record<string, string> = {
  regret: "Extra modelled cost versus hindsight optimum",
  runtime_ms: "Runtime (milliseconds)",
  compute_cost: "Retrieval operator cost units",
  affected_path_recall: "Affected routes found (0–1)",
  exposure_mae: "Exposure error (lower is better)",
  recall_at_k: "Relevant examples found (0–1)",
  context_precision: "Relevant share of retrieved context",
  raw_score_ece: "Coverage score calibration error",
  rule_router: "Rule-based controller",
  learned_mlp: "Learned controller",
  llm_planner: "LLM planner",
  graph_timeseries: "Graph and time-series retrieval",
};
const label = (text: string) => descriptions[text] ?? text.replace(/_/g, " ");
function valueText(value: unknown): string {
  if (value === null || value === undefined) return "Not defined";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (typeof value === "object" && "mean" in value) {
    const metric = value as {mean: number; ci95: number[]; n: number};
    return `${valueText(metric.mean)} (95% CI ${valueText(metric.ci95[0])}–${valueText(metric.ci95[1])}; n=${metric.n})`;
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function EvaluationResults() {
  const [report, setReport] = useState<Phase8Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [scale, setScale] = useState("v1_corridor");
  const [selected, setSelected] = useState(1);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    asciApi.getPhase8Evaluation().then(data => {
      if (active) {
        setReport(data);
        setScale(current => data.network_scales.includes(current) ? current : data.network_scales[0]);
        setSelected(current => data.selected_studies.includes(current) ? current : data.selected_studies[0]);
      }
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to read evaluation reports"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  const study = report?.studies.find(item => item.study === selected && item.network_scale === scale);
  async function download() {
    try {
      const data = await asciApi.getAblationReport(selected, scale);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = `study_${selected}_${scale}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : "Download failed"); }
  }
  return <section className="space-y-4 rounded-md border border-light-border bg-white p-4 dark:border-dark-border dark:bg-dark-card" aria-label="Measured Phase 8 results">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 className="font-bold">Phase 8 · Measured benchmark results</h3>
        <p className="text-sm text-light-text-secondary dark:text-dark-text-secondary">Compare a component with alternatives to see what it adds. Completion means the evaluation ran; research targets are shown separately.</p>
      </div>
      <button type="button" disabled={loading} onClick={() => setRevision(x => x + 1)} className="rounded border px-3 py-1 disabled:opacity-50">Refresh results</button>
    </div>
    {loading && <p role="status">Loading measured reports…</p>}
    {error && <p role="alert" className="rounded border border-amber-400 p-3 text-sm">{error}</p>}
    {report && <>
      <p className="text-sm">{report.studies.filter(x => x.completed).length} of {report.selected_studies.length * report.network_scales.length} study runs verified · {report.completed ? "Selected evaluations complete" : "Evaluation incomplete"}</p>
      <label className="flex items-center gap-2 text-sm">Network size
        <select value={scale} onChange={event => setScale(event.target.value)} className="rounded border bg-white p-1 dark:bg-dark-surface">
          {report.network_scales.map(item => <option key={item} value={item}>{item === "v0_core" ? "Core network" : "Full corridor"}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap gap-2" aria-label="Ablation studies">
        {report.selected_studies.map(id => <button type="button" key={id} onClick={() => setSelected(id)} aria-pressed={selected === id}
          className={`rounded border px-3 py-2 text-sm ${selected === id ? "bg-blue-600 text-white" : "hover:bg-blue-50 dark:hover:bg-dark-hover"}`}>{id}. {titles[id]}</button>)}
      </div>
      {study ? <div className="space-y-4">
        <div className="flex items-center justify-between gap-2"><h4 className="font-bold">{titles[study.study]}</h4><button type="button" onClick={download} className="rounded border px-3 py-1 text-sm">Download measured JSON</button></div>
        {!!Object.keys(study.targets).length && <ul className="space-y-1 text-sm">{Object.entries(study.targets).map(([key, met]) => <li key={key}>{label(key)}: <strong className={met ? "text-green-700 dark:text-green-400" : "text-amber-700 dark:text-amber-400"}>{met ? "Target met" : "Target not met"}</strong></li>)}</ul>}
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="p-2">Variant</th><th className="p-2">Measurement</th><th className="p-2">Result</th></tr></thead>
          <tbody>{Object.entries(study.summary).flatMap(([variant, metrics]) => Object.entries(metrics).map(([metric, value]) => <tr key={`${variant}-${metric}`} className="border-b border-light-border dark:border-dark-border"><td className="p-2">{label(variant)}</td><td className="p-2">{label(metric)}</td><td className="p-2 font-mono text-xs">{valueText(value)}</td></tr>))}</tbody>
        </table></div>
        {study.adaptive_metrics && <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="mb-2 text-left font-semibold">Controller quality and operator cost savings</caption><thead><tr><th className="p-2">Controller</th><th className="p-2">Savings</th><th className="p-2">AUROC</th><th className="p-2">Calibration error</th><th className="p-2">Targets</th></tr></thead><tbody>{Object.entries(study.adaptive_metrics).map(([variant, metrics]) => <tr key={variant} className="border-t"><td className="p-2">{label(variant)}</td><td className="p-2">{metrics.compute_savings === null ? "Not defined" : `${(metrics.compute_savings * 100).toFixed(1)}%`}</td><td className="p-2">{valueText(metrics.auroc)}</td><td className="p-2">{valueText(metrics.ece)}</td><td className="p-2">{Object.entries(metrics.targets).map(([key, met]) => `${key}: ${met ? "met" : "not met"}`).join("; ")}</td></tr>)}</tbody></table></div>}
        <div className="rounded border border-amber-300 p-3 text-sm"><h5 className="mb-2 font-semibold">How to interpret this study</h5><ul className="list-disc space-y-1 pl-5">{study.limitations.map(text => <li key={text}>{text}</li>)}</ul></div>
      </div> : <p>No measured result is available for this study and network size.</p>}
    </>}
  </section>;
}
