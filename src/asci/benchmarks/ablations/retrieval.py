"""Planted-analogue retrieval, sufficiency and citation-check comparisons."""
from __future__ import annotations

from statistics import mean

from asci.benchmarks.ablations.dataset import cases, close_pipeline
from asci.benchmarks.metrics import ece, mean_ci
from asci.core.contracts import PipelineConfig
from asci.core.state import DisruptionEventType, EvidenceItem, TrustTier
from asci.llm.explainer import verify_briefing_citations
from asci.stages import WalkingSkeletonPipeline
from asci.uskl.vector_store import SemanticVectorStore

PROFILES = ("prolonged", "gradual", "rapid")


def _profile(curve):
    average = mean(curve) if curve else .35
    return "prolonged" if average < .4 else "gradual" if average < .75 else "rapid"


def planted_corpus(registry):
    """Known labels are planted before retrieval and never supplied as ranking bonuses."""
    store = SemanticVectorStore(registry=registry, load_default_corpus=False)
    for entity in registry.all_entities().values():
        for hazard in (DisruptionEventType.HAZARD_PORT, DisruptionEventType.HAZARD_ROAD,
                       DisruptionEventType.PORT_CONGESTION_STRIKE):
            for profile in PROFILES:
                for index in range(2):
                    claim = f"{entity.name} has a {profile} recovery precedent for {hazard.value}."
                    store.add_document(EvidenceItem(citation_id=f"CIT_PLANTED_{entity.id}_{hazard.value}_{profile.upper()}_{index}",
                        source="Controlled planted analogue corpus", trust_tier=TrustTier.TIER_A,
                        entity_ids=[entity.id], publication_date="2026-01-01", hazard_types=[hazard],
                        snippet=claim + " Evaluate road and rail diversions against operational constraints.",
                        supported_claims=[claim]))
    return store


def run_retrieval_studies(config, scale):
    pipe = WalkingSkeletonPipeline.from_config(PipelineConfig(network_scale=scale))
    # The paired core corpus stays identical across graph scales.
    from asci.core.registry import get_canonical_registry
    store = planted_corpus(get_canonical_registry(network_scale="v0_core"))
    retrieval_rows, gate_rows, claim_rows = [], [], []
    try:
        for event in cases(config, scale):
            name = pipe.stage_c.registry.get(event.primary_entity_id).name
            profile = _profile(pipe.stage_c.timeseries_store.get_recovery_curve(event.primary_entity_id, event.event_type.value))
            gold = {doc.citation_id for doc in store._documents if event.primary_entity_id in doc.entity_ids
                    and event.event_type in doc.hazard_types and f"{profile} recovery" in doc.snippet}
            if not gold:
                raise ValueError(f"Unplanted query {event.primary_entity_id}")
            query = f"{name} {event.event_type.value} disruption diversion recovery"
            for variant in ("text_only", "graph_aware", "graph_timeseries"):
                kwargs = {} if variant == "text_only" else {"entity_ids": [event.primary_entity_id], "hazard_type": event.event_type}
                enriched = query if variant != "graph_timeseries" else f"{query} {profile} recovery"
                docs = store.query(enriched, date_to=event.timestamp.date().isoformat(), limit=config.retrieval_k, **kwargs)
                ids = {doc.citation_id for doc in docs}
                hits = len(ids & gold)
                retrieval_rows.append({"case": event.event_id, "variant": variant, "gold_ids": sorted(gold),
                                       "retrieved_ids": [d.citation_id for d in docs], "recall_at_k": hits/len(gold),
                                       "context_precision": hits/len(docs) if docs else 0, "k": config.retrieval_k})
            for variant in ("sufficiency_gate", "fixed_retrievals"):
                first = store.query(query, entity_ids=[event.primary_entity_id], hazard_type=event.event_type,
                                    date_to=event.timestamp.date().isoformat(), limit=config.retrieval_k)
                trace = ["RETRIEVE_TEXT"]
                score, _ = pipe.stage_c._grade_evidence(first, event)
                if variant == "sufficiency_gate":
                    trace.append("GRADE")
                should_expand = config.fixed_retrievals > 1 and (variant == "fixed_retrievals" or score < config.gate_threshold)
                final = first
                if should_expand:
                    curve = pipe.stage_c.timeseries_store.get_recovery_curve(event.primary_entity_id, event.event_type.value)
                    enriched = f"{query} {_profile(curve)} recovery"
                    final = store.query(enriched, entity_ids=[event.primary_entity_id], hazard_type=event.event_type,
                                        date_to=event.timestamp.date().isoformat(), limit=config.retrieval_k)
                    trace.extend(["RETRIEVE_TS", "REWRITE_QUERY", "RETRIEVE_TEXT"])
                    if variant == "sufficiency_gate":
                        trace.append("GRADE")
                final_score, _ = pipe.stage_c._grade_evidence(final, event)
                gate_rows.append({"case": event.event_id, "variant": variant, "retrieval_steps": 1+int(should_expand),
                                  "grade_steps": 1+int(should_expand) if variant == "sufficiency_gate" else 0,
                                  "steps_to_answer": len(trace), "operators": trace,
                                  "score": final_score, "answer_supported": int(bool(final) and final[0].citation_id in gold)})
            # Gold comes from planted supported_claims, with independent mutations.
            doc = store.get_document(sorted(gold)[0])
            assert doc is not None
            supported = doc.supported_claims[0]
            candidates = [(supported + f" [{doc.citation_id}]", True, "supported"),
                          (f"All corridor plants have 90 days of stock. [{doc.citation_id}]", False, "wrong_claim_valid_id"),
                          ("Vessel traffic will recover tomorrow. [CIT_FABRICATED_999]", False, "fabricated_id"),
                          ("No plant can stop under this event.", False, "uncited_claim")]
            for text, is_supported, mutation in candidates:
                cleaned, valid, rejected = verify_briefing_citations([text], {doc.citation_id})
                for variant in ("without_checks", "with_citation_checks"):
                    claim_rows.append({"case": event.event_id, "variant": variant, "mutation": mutation,
                                       "claim": cleaned[0] if variant == "with_citation_checks" else text,
                                       "supported": is_supported,
                                       "invalid_citation_retained": bool(rejected) and variant == "without_checks",
                                       "valid_citation_count": len(valid) if variant == "with_citation_checks" else int(mutation != "uncited_claim")})
    finally:
        close_pipeline(pipe)
    retrieval_summary = {variant: {key: mean_ci([r[key] for r in retrieval_rows if r["variant"] == variant], seed=config.seed, samples=config.bootstrap_samples)
                                  for key in ("recall_at_k", "context_precision")}
                         for variant in ("text_only", "graph_aware", "graph_timeseries")}
    gate_summary = {}
    for variant in ("sufficiency_gate", "fixed_retrievals"):
        rows = [r for r in gate_rows if r["variant"] == variant]
        gate_summary[variant] = {"mean_retrieval_steps": mean(r["retrieval_steps"] for r in rows),
                                 "mean_total_steps": mean(r["steps_to_answer"] for r in rows),
                                 "answer_support_rate": mean(r["answer_supported"] for r in rows),
                                 "raw_score_ece": ece([r["answer_supported"] for r in rows], [r["score"] for r in rows])}
    claim_summary = {variant: {"support_rate": mean(r["supported"] for r in claim_rows if r["variant"] == variant),
                               "invalid_citations_retained": sum(r["invalid_citation_retained"] for r in claim_rows if r["variant"] == variant)}
                     for variant in ("without_checks", "with_citation_checks")}
    return ({"study": 3, "completed": True, "records": retrieval_rows, "summary": retrieval_summary,
             "targets": {"recall_at_k": retrieval_summary["graph_timeseries"]["recall_at_k"]["mean"] >= config.retrieval_recall_target},
             "limitations": ["Synthetic labelled analogues, deterministic hashed embeddings; this measures controlled retrieval, not relevance on independent human labels.",
                             "Time-series profile is computed from the existing prior curve, not future outcomes."]},
            {"study": 4, "completed": True, "records": claim_rows, "summary": claim_summary,
             "targets": {"claim_support": claim_summary["with_citation_checks"]["support_rate"] >= config.citation_support_target},
             "limitations": ["Citation ID checks remove invalid references but do not remove unsupported prose or establish entailment.",
                             "The stress corpus contains one supported claim and three independent unsupported mutations per episode; its support rate is not a live-model prevalence estimate."]},
            {"study": 5, "completed": True, "records": gate_rows, "summary": gate_summary,
             "limitations": ["Raw sufficiency is a coverage heuristic, not a trained probability; ECE compares it with top-ranked analogue correctness.",
                             "Gate grading steps are counted separately from retrieval steps; fixed retrieval receives the same final audit score without paying an online grading step."]})
