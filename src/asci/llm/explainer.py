"""
Citation-Verified RAG + LLM Executive Briefing Generator for Stage E.
Synthesizes verified OR-Tools allocations, plant line-stop risks, and evidence citations
into a concise control-tower briefing without ever fabricating metrics or citation IDs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from asci.core.contracts import PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import PipelineState
from asci.llm.client import MultiProviderLLMClient

_CIT_PATTERN = re.compile(r"\[(CIT_[A-Z0-9_]+)\]|\b(CIT_[A-Z0-9_]+)\b")

_BRIEFING_SYSTEM_PROMPT = """You are an automotive supply-chain resilience analyst summarizing a verified OR-Tools mitigation plan.
Strict grounding rules:
1. Report ONLY metrics and route paths supplied in the structured JSON context. Never invent percentages, TEU numbers, plant names, or costs from outside knowledge or playbook examples.
2. Use the provided exact `plan.road_pct`, `plan.rail_pct`, `plan.total_delivered_teu`, `plan.objective_cost`, and `plan.unmet_demand_teu` percentages/totals.
3. Prefer human-readable facility names (e.g. "Chennai Port Trust", "Sriperumbudur Assembly Hub") over raw uppercase node IDs in prose.
4. When referencing disaster playbooks or evidence, cite them using exact brackets like [CIT_PLAYBOOK_CYCLONE_001] from `available_citations` ONLY.
5. Return ONLY valid JSON with keys:
{
  "headline": "concise 1-sentence executive headline",
  "executive_summary": "2-3 clear sentences summarizing impact, verified Road/Rail split, and zero/non-zero shortfall with [CIT_...] tags",
  "key_actions": ["action 1", "action 2", "action 3"],
  "line_stop_watchouts": ["watchout 1", ...]
}
"""


def verify_briefing_citations(
    text_items: list[str],
    valid_citation_ids: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Validate `[CIT_...]` references across generated prose.
    Returns `(cleaned_texts, verified_citations, rejected_citations)`.
    """
    verified: list[str] = []
    rejected: list[str] = []
    cleaned_list: list[str] = []

    for item in text_items:
        def _replace(match: re.Match[str]) -> str:
            cid = match.group(1) or match.group(2)
            if cid in valid_citation_ids:
                if cid not in verified:
                    verified.append(cid)
                return f"[{cid}]"
            if cid not in rejected:
                rejected.append(cid)
            return "[UNVERIFIED_CIT_REMOVED]"

        cleaned = _CIT_PATTERN.sub(_replace, item)
        cleaned_list.append(cleaned)

    return cleaned_list, verified, rejected


def _strip_json_fences(raw_text: str) -> str:
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    brace_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    return brace_match.group(0).strip() if brace_match else cleaned


class PlanBriefingGenerator:
    """Generates citation-verified RAG & LLM executive briefings for Stage E."""

    def __init__(
        self,
        llm_client: MultiProviderLLMClient | None = None,
        registry: CanonicalEntityRegistry | None = None,
    ) -> None:
        self.llm_client = llm_client or MultiProviderLLMClient()
        self.registry = registry or get_canonical_registry()

    def _build_deterministic_briefing(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        *,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        event = state.event
        plan = state.candidate_plan
        graph_ctx = state.graph_context
        verif = state.verification_report

        top_cits = [doc.citation_id for doc in state.evidence_set[:3]]
        cit_suffix = " " + " ".join(f"[{c}]" for c in top_cits) if top_cits else ""

        if not event or not plan:
            return {
                "mode": "deterministic_grounded",
                "provider": "deterministic",
                "model": "deterministic-offline",
                "headline": "Awaiting complete mitigation plan.",
                "executive_summary": (
                    f"Session {state.session_id} ended with status {state.status.value}.{cit_suffix}"
                ),
                "key_actions": [],
                "line_stop_watchouts": [],
                "cited_ids": top_cits,
                "rejected_citations": [],
                "citation_verified": True,
                "fallback_reason": fallback_reason,
            }

        primary_name = (
            self.registry.get(event.primary_entity_id).name
            if self.registry.validate_id(event.primary_entity_id)
            else event.primary_entity_id
        )
        verdict = verif.overall_verdict.value if verif else "UNVERIFIED"
        headline = (
            f"{event.event_type.value} at {primary_name} "
            f"(severity {round(event.severity * 100)}%): Plan {plan.plan_id} {verdict}"
        )

        rail_pct = round(plan.mode_split.get("INTERMODAL_RAIL", 0.0) * 100.0, 1)
        road_pct = round(plan.mode_split.get("ROAD", 0.0) * 100.0, 1)
        delivered_teu = round(sum(a.flow_teu for a in plan.allocations), 1)
        summary = (
            f"Following disruption at {primary_name} ({event.estimated_duration_days}d), "
            f"{plan.solver_engine} ({plan.risk_mode}) routed {delivered_teu} TEU across "
            f"{len(plan.allocations)} verified allocations ({road_pct}% Road / {rail_pct}% Rail) "
            f"at cost {round(plan.objective_cost, 1):,} and {round(plan.unmet_demand_teu, 1)} TEU unmet demand."
            f"{cit_suffix}"
        )

        top_allocs = sorted(plan.allocations, key=lambda a: a.flow_teu, reverse=True)[:3]
        key_actions = []
        for a in top_allocs:
            orig_name = (
                self.registry.get(a.origin_id).name
                if self.registry.validate_id(a.origin_id)
                else a.origin_id
            )
            dest_name = (
                self.registry.get(a.destination_id).name
                if self.registry.validate_id(a.destination_id)
                else a.destination_id
            )
            mode_label = "Intermodal Rail" if "RAIL" in a.mode else "Road"
            key_actions.append(
                f"Move {round(a.flow_teu, 1)} TEU ({a.commodity}) from {orig_name} to {dest_name} via {mode_label} ({len(a.path) - 1} hops)."
            )
        if top_cits:
            key_actions.append(
                f"Execute regional diversion SOP guidance from retrieved citations {', '.join(f'[{c}]' for c in top_cits)}."
            )

        watchouts: list[str] = []
        if graph_ctx:
            critical = sorted(
                graph_ctx.line_stop_metrics,
                key=lambda m: (m.time_to_line_stop_days, -m.line_stop_risk),
            )[:3]
            for ls in critical:
                plant_name = (
                    self.registry.get(ls.plant_id).name
                    if self.registry.validate_id(ls.plant_id)
                    else ls.plant_id
                )
                watchouts.append(
                    f"{plant_name}: {ls.days_of_cover}d inventory vs {ls.expected_delay_days}d delay "
                    f"(TTLS {ls.time_to_line_stop_days}d, line-stop risk {round(ls.line_stop_risk * 100, 1)}%)."
                )

        if plan.unmet_demand_teu > 0.0:
            watchouts.insert(
                0,
                f"Corridor shortfall of {round(plan.unmet_demand_teu, 1)} TEU remains under {cfg.network_scale} topology; consider air-freight or buffer draw.",
            )

        return {
            "mode": "deterministic_grounded",
            "provider": "deterministic",
            "model": "deterministic-offline",
            "headline": headline,
            "executive_summary": summary,
            "key_actions": key_actions,
            "line_stop_watchouts": watchouts,
            "cited_ids": top_cits,
            "rejected_citations": [],
            "citation_verified": True,
            "fallback_reason": fallback_reason,
        }

    def generate(self, state: PipelineState, cfg: PipelineConfig) -> dict[str, Any]:
        """
        Generate an executive RAG briefing.
        Uses live LLM synthesis only when `cfg.enable_llm` is True and a provider is available;
        otherwise returns the deterministic grounded briefing.
        """
        if not cfg.enable_llm or not state.event or not state.candidate_plan:
            return self._build_deterministic_briefing(state, cfg)

        event = state.event
        plan = state.candidate_plan
        verif = state.verification_report
        valid_cits = {doc.citation_id for doc in state.evidence_set}

        top_allocs = sorted(plan.allocations, key=lambda a: a.flow_teu, reverse=True)[:5]
        watchouts_ctx = (
            [
                {
                    "plant_id": ls.plant_id,
                    "plant_name": (
                        self.registry.get(ls.plant_id).name
                        if self.registry.validate_id(ls.plant_id)
                        else ls.plant_id
                    ),
                    "days_of_cover": ls.days_of_cover,
                    "expected_delay_days": ls.expected_delay_days,
                    "time_to_line_stop_days": ls.time_to_line_stop_days,
                    "line_stop_risk_pct": round(ls.line_stop_risk * 100.0, 1),
                }
                for ls in sorted(
                    state.graph_context.line_stop_metrics,
                    key=lambda m: m.time_to_line_stop_days,
                )[:5]
            ]
            if state.graph_context
            else []
        )

        road_pct = round(plan.mode_split.get("ROAD", 0.0) * 100.0, 1)
        rail_pct = round(plan.mode_split.get("INTERMODAL_RAIL", 0.0) * 100.0, 1)
        delivered_teu = round(sum(a.flow_teu for a in plan.allocations), 1)
        primary_name = (
            self.registry.get(event.primary_entity_id).name
            if self.registry.validate_id(event.primary_entity_id)
            else event.primary_entity_id
        )

        context_payload = {
            "network_scale": cfg.network_scale,
            "event": {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "primary_entity_id": event.primary_entity_id,
                "primary_entity_name": primary_name,
                "severity_pct": round(event.severity * 100.0, 1),
                "duration_days": event.estimated_duration_days,
                "headline": event.raw_headline,
            },
            "plan": {
                "plan_id": plan.plan_id,
                "solver_engine": plan.solver_engine,
                "risk_mode": plan.risk_mode,
                "objective_cost": round(plan.objective_cost, 1),
                "total_delivered_teu": delivered_teu,
                "unmet_demand_teu": round(plan.unmet_demand_teu, 1),
                "road_pct": road_pct,
                "rail_pct": rail_pct,
                "top_allocations": [
                    {
                        "commodity": a.commodity,
                        "origin_name": (
                            self.registry.get(a.origin_id).name
                            if self.registry.validate_id(a.origin_id)
                            else a.origin_id
                        ),
                        "destination_name": (
                            self.registry.get(a.destination_id).name
                            if self.registry.validate_id(a.destination_id)
                            else a.destination_id
                        ),
                        "mode": a.mode,
                        "flow_teu": a.flow_teu,
                    }
                    for a in top_allocs
                ],
            },
            "verification": {
                "passed": verif.passed if verif else False,
                "failed_checks": verif.failed_checks if verif else [],
            },
            "plant_line_stop_risks": watchouts_ctx,
            "available_citations": [
                {
                    "citation_id": d.citation_id,
                    "trust_tier": d.trust_tier.value,
                    "entity_ids": d.entity_ids,
                    "snippet": d.snippet[:280],
                }
                for d in state.evidence_set
            ],
        }

        completion = self.llm_client.complete(
            system_prompt=_BRIEFING_SYSTEM_PROMPT,
            user_prompt=(
                "Generate an executive supply-chain briefing from this verified state JSON:\n\n"
                f"{json.dumps(context_payload, indent=2)}"
            ),
            json_mode=True,
            temperature=0.0,
            provider_override=cfg.llm_provider,
        )

        if not completion.used_live_llm:
            return self._build_deterministic_briefing(
                state,
                cfg,
                fallback_reason=completion.fallback_reason,
            )

        try:
            parsed = json.loads(_strip_json_fences(completion.text))
            headline = str(parsed.get("headline", "")).strip()
            summary = str(parsed.get("executive_summary", "")).strip()
            actions = [str(x).strip() for x in (parsed.get("key_actions") or []) if str(x).strip()][:5]
            watchouts = [
                str(x).strip() for x in (parsed.get("line_stop_watchouts") or []) if str(x).strip()
            ][:5]

            if not headline or not summary:
                raise ValueError("LLM briefing missing required headline/executive_summary fields")

            cleaned_bundle, verified_cits, rejected_cits = verify_briefing_citations(
                [headline, summary, *actions, *watchouts],
                valid_cits,
            )
            c_head = cleaned_bundle[0]
            c_summary = cleaned_bundle[1]
            c_actions = cleaned_bundle[2 : 2 + len(actions)]
            c_watchouts = cleaned_bundle[2 + len(actions) :]

            # Ensure retrieved Tier A/B evidence is still surfaced if LLM omitted bracket tags
            if valid_cits and not verified_cits:
                verified_cits = [d.citation_id for d in state.evidence_set[:2]]
                c_summary = f"{c_summary} " + " ".join(f"[{c}]" for c in verified_cits)

            return {
                "mode": "live_llm",
                "provider": completion.provider,
                "model": completion.model,
                "latency_ms": completion.latency_ms,
                "headline": c_head,
                "executive_summary": c_summary,
                "key_actions": c_actions,
                "line_stop_watchouts": c_watchouts,
                "cited_ids": verified_cits,
                "rejected_citations": rejected_cits,
                "citation_verified": len(rejected_cits) == 0,
                "fallback_reason": (
                    f"Stripped unverified citations: {rejected_cits}" if rejected_cits else None
                ),
            }
        except Exception as exc:
            return self._build_deterministic_briefing(
                state,
                cfg,
                fallback_reason=f"LLM briefing parse error ({type(exc).__name__}); used deterministic grounded summary.",
            )

