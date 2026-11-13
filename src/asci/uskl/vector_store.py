"""
Tagged Semantic Vector Memory for Disaster Bulletins & Mitigation Playbooks.
Supports FAISS IndexFlatIP (when installed) and deterministic L2-normalized NumPy cosine search,
with structured metadata filtering (entity_ids, region, hazard_type, date, TrustTier)
and index persistence.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import (
    DisruptionEvent,
    DisruptionEventType,
    EvidenceItem,
    MitigationPlan,
    TrustTier,
)

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - optional FAISS backend
    faiss = None


class EmbeddingBackend(Protocol):
    """Protocol for deterministic dense vector encoders."""

    @property
    def dim(self) -> int: ...

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into L2-normalized float32 embeddings of shape (N, dim)."""
        ...


class HashedDenseEncoder:
    """
    Deterministic, zero-download fallback encoder using stable blake2b feature hashing
    over word unigrams, domain synonym concepts, bigrams, and character 4-grams.
    """

    _CONCEPT_SYNONYMS: dict[str, str] = {
        "typhoon": "cyclone",
        "cyclonic": "cyclone",
        "tempest": "cyclone",
        "storm": "cyclone",
        "surge": "cyclone",
        "gale": "cyclone",
        "dockworker": "stevedore",
        "dockworkers": "stevedore",
        "longshoreman": "stevedore",
        "longshoremen": "stevedore",
        "harbor": "berth",
        "harbour": "berth",
        "wharf": "berth",
        "jetty": "berth",
        "quay": "berth",
        "stoppage": "disruption",
        "blockage": "disruption",
        "closure": "disruption",
        "shutdown": "disruption",
        "halted": "disruption",
        "suspended": "disruption",
        "flooding": "waterlogging",
        "inundation": "waterlogging",
        "inundated": "waterlogging",
        "waterlogged": "waterlogging",
        "railhead": "rail",
        "intermodal": "rail",
    }

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return "hashed-concept-bow"

    @staticmethod
    def _stable_bucket(token: str, dim: int) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        val = int.from_bytes(digest[:4], "little")
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        return val % dim, sign

    def encode_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        words = re.findall(r"[a-z0-9_]+", text.lower())
        if not words:
            return vec

        features: dict[str, float] = {}
        # Word unigrams (higher weight) + concept canonicalization for offline synonym matching
        for w in words:
            features[f"w:{w}"] = features.get(f"w:{w}", 0.0) + 1.5
            canon = self._CONCEPT_SYNONYMS.get(w)
            if canon:
                features[f"syn:{canon}"] = features.get(f"syn:{canon}", 0.0) + 1.25
            # Character 4-grams for morphological / spelling robustness
            if len(w) >= 4:
                for i in range(len(w) - 3):
                    cg = w[i : i + 4]
                    features[f"c:{cg}"] = features.get(f"c:{cg}", 0.0) + 0.35

        # Word bigrams
        for i in range(len(words) - 1):
            bg = f"b:{words[i]}_{words[i + 1]}"
            features[bg] = features.get(bg, 0.0) + 1.2

        for feat, count in features.items():
            idx, sign = self._stable_bucket(feat, self._dim)
            vec[idx] += sign * (1.0 + math.log(count))

        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return np.vstack([self.encode_one(t) for t in texts]).astype(np.float32)


_DELIM_TAG_RE = re.compile(r"</?\s*UNTRUSTED_DOCUMENT\s*>", flags=re.IGNORECASE)


class SemanticVectorStore:
    """
    Tagged Semantic Vector Store backed by FAISS (when installed) or NumPy cosine index.
    Enforces Canonical Entity Registry grounding, trust-tier weighting, and expiry filtering.
    """

    _TRUST_WEIGHTS = {
        TrustTier.TIER_A: 1.00,
        TrustTier.TIER_B: 0.80,
        TrustTier.TIER_C: 0.45,
    }
    _TIER_RANK = {
        TrustTier.TIER_A: 3,
        TrustTier.TIER_B: 2,
        TrustTier.TIER_C: 1,
    }

    def __init__(
        self,
        registry: CanonicalEntityRegistry | None = None,
        encoder: EmbeddingBackend | None = None,
        corpus_path: str | Path | None = None,
        load_default_corpus: bool = True,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.encoder: EmbeddingBackend = encoder or HashedDenseEncoder(dim=384)
        self._documents: list[EvidenceItem] = []
        self._vectors: np.ndarray = np.zeros((0, self.encoder.dim), dtype=np.float32)
        self._faiss_index = faiss.IndexFlatIP(self.encoder.dim) if faiss is not None else None

        if load_default_corpus:
            self._load_corpus(corpus_path)

    @property
    def backend_name(self) -> str:
        return "faiss" if self._faiss_index is not None else "numpy"

    @property
    def encoder_backend(self) -> str:
        return getattr(self.encoder, "name", type(self.encoder).__name__)

    def _document_text(self, doc: EvidenceItem) -> str:
        claims = " ".join(doc.supported_claims)
        entities = " ".join(doc.entity_ids)
        region = doc.region or ""
        hazards = " ".join(h.value for h in doc.hazard_types)
        return f"{doc.source} {region} {hazards} {entities} {doc.snippet} {claims}"

    def add_document(self, doc: EvidenceItem) -> None:
        """Index an evidence document after validating referenced entity IDs."""
        for entity_id in doc.entity_ids:
            if not self.registry.validate_id(entity_id):
                raise ValueError(
                    f"Evidence document references ungrounded entity ID '{entity_id}'."
                )

        # Enforce untrusted quoting marker and strip closing delimiter tags on indexed docs
        sanitized_snippet = _DELIM_TAG_RE.sub("[UNTRUSTED_DELIMITER]", doc.snippet)
        updates: dict[str, Any] = {}
        if not doc.untrusted_quoted:
            updates["untrusted_quoted"] = True
        if sanitized_snippet != doc.snippet:
            updates["snippet"] = sanitized_snippet
        safe_doc = doc.model_copy(update=updates) if updates else doc
        vec = self.encoder.encode([self._document_text(safe_doc)])

        existing_idx = next(
            (i for i, existing in enumerate(self._documents) if existing.citation_id == safe_doc.citation_id),
            None,
        )
        if existing_idx is not None:
            self._documents[existing_idx] = safe_doc
            self._vectors[existing_idx] = vec[0]
            if self._faiss_index is not None:
                self._faiss_index.reset()
                if self._vectors.shape[0] > 0:
                    self._faiss_index.add(self._vectors)
            return

        self._documents.append(safe_doc)
        if self._vectors.shape[0] == 0:
            self._vectors = vec
        else:
            self._vectors = np.vstack([self._vectors, vec])

        if self._faiss_index is not None:
            self._faiss_index.add(vec)

    def index_validated_decision_playbook(
        self,
        *,
        event: DisruptionEvent,
        plan: MitigationPlan,
        decision: str,
        planner_id: str,
        comments: str = "",
        modifications: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        """
        Loop L4: Index a human-approved or edited mitigation plan into SemanticVectorStore
        as a reusable analogue playbook citation (`CIT_L4_DECISION_...`).
        """
        norm_decision = decision.strip().upper()
        suffix = plan.plan_id.split("_")[-1][:8].upper()
        citation_id = f"CIT_L4_DECISION_{suffix}"

        grounded_entities = [
            eid
            for eid in dict.fromkeys([event.primary_entity_id, *event.affected_entity_ids])
            if self.registry.validate_id(eid)
        ]
        primary_ent = self.registry.get(event.primary_entity_id)
        rail_pct = round(float(plan.mode_split.get("INTERMODAL_RAIL", 0.0)) * 100.0, 1)
        top_ports = sorted(
            {a.origin_id for a in plan.allocations[:5] if self.registry.validate_id(a.origin_id)}
        )
        mod_note = f" Planner overrides: {json.dumps(modifications)}." if modifications else ""
        comment_note = f" Notes: {comments.strip()}." if comments.strip() else ""

        snippet = (
            f"Human-validated Loop L4 analogue playbook ({norm_decision} by {planner_id}) for "
            f"{event.event_type.value} at {primary_ent.name} ({event.primary_entity_id}): "
            f"routed freight across {', '.join(top_ports) or event.primary_entity_id} with "
            f"{rail_pct}% intermodal rail mode share, objective cost ${plan.objective_cost:,.0f}, "
            f"and {plan.unmet_demand_teu:.1f} TEU unmet demand.{comment_note}{mod_note}"
        )

        item = EvidenceItem(
            citation_id=citation_id,
            source=f"ASCI Loop L4 Verified Decision Memory ({norm_decision})",
            trust_tier=TrustTier.TIER_A if norm_decision == "APPROVE" else TrustTier.TIER_B,
            entity_ids=grounded_entities,
            region=primary_ent.region,
            hazard_types=[event.event_type],
            snippet=snippet,
            publication_date=event.timestamp.strftime("%Y-%m-%d"),
            supported_claims=[
                f"{event.primary_entity_id} {event.event_type.value} validated at {rail_pct}% rail mode share.",
                f"Unmet demand stabilized at {plan.unmet_demand_teu:.1f} TEU under {plan.risk_mode}.",
            ],
            relevance_score=0.92,
            untrusted_quoted=True,
        )
        self.add_document(item)
        return item

    def add_documents(self, docs: list[EvidenceItem]) -> None:
        """Batch-index multiple evidence documents."""
        for doc in docs:
            self.add_document(doc)

    def query(
        self,
        query_text: str,
        entity_ids: list[str] | None = None,
        region: str | None = None,
        hazard_type: DisruptionEventType | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        min_trust_tier: TrustTier | None = None,
        include_expired: bool = False,
        as_of_date: str | None = None,
        limit: int = 5,
    ) -> list[EvidenceItem]:
        """
        Retrieve relevant evidence passages filtered by metadata tags and weighted by TrustTier.
        """
        if not self._documents:
            return []

        ref_date = as_of_date or datetime.now(UTC).strftime("%Y-%m-%d")
        min_rank = self._TIER_RANK.get(min_trust_tier, 0) if min_trust_tier else 0
        region_low = region.lower() if region else None

        # Determine eligible candidate indices based on metadata filters
        eligible_indices: list[int] = []
        for idx, doc in enumerate(self._documents):
            if self._TIER_RANK.get(doc.trust_tier, 0) < min_rank:
                continue

            if not include_expired and doc.expires_at and doc.expires_at <= ref_date:
                continue

            if entity_ids:
                if not any(eid in doc.entity_ids for eid in entity_ids):
                    continue

            if region_low and (not doc.region or doc.region.lower() != region_low):
                continue

            if hazard_type and (hazard_type not in doc.hazard_types):
                continue

            if date_from and doc.publication_date < date_from:
                continue

            if date_to and doc.publication_date > date_to:
                continue

            eligible_indices.append(idx)

        if not eligible_indices:
            return []

        q_vec = self.encoder.encode([query_text])

        # Compute cosine similarities via FAISS or NumPy dot product
        if self._faiss_index is not None:
            scores_arr, indices_arr = self._faiss_index.search(q_vec, len(self._documents))
            sim_by_idx = {
                int(doc_idx): float(sim)
                for doc_idx, sim in zip(indices_arr[0], scores_arr[0], strict=True)
                if doc_idx >= 0
            }
        else:
            sims = (self._vectors @ q_vec[0]).tolist()
            sim_by_idx = {idx: float(sims[idx]) for idx in range(len(self._documents))}

        ranked: list[tuple[float, EvidenceItem]] = []
        for idx in eligible_indices:
            doc = self._documents[idx]
            raw_sim = max(0.0, sim_by_idx.get(idx, 0.0))

            # Entity overlap boost + trust-tier calibration
            entity_overlap = 0.0
            if entity_ids:
                matched_count = sum(1 for eid in entity_ids if eid in doc.entity_ids)
                entity_overlap = 0.15 * min(1.0, matched_count / max(len(entity_ids), 1))

            trust_weight = self._TRUST_WEIGHTS.get(doc.trust_tier, 0.7)
            weighted_score = min(1.0, round((raw_sim + entity_overlap) * trust_weight, 4))
            scored_doc = doc.model_copy(update={"relevance_score": weighted_score})
            ranked.append((weighted_score, scored_doc))

        ranked.sort(key=lambda item: (-item[0], item[1].citation_id))
        return [doc for _, doc in ranked[:limit]]

    def get_document(self, citation_id: str) -> EvidenceItem | None:
        """Retrieve a specific EvidenceItem by its canonical citation_id."""
        for doc in self._documents:
            if doc.citation_id == citation_id:
                return doc
        return None

    def save_index(self, directory: str | Path) -> Path:
        """Persist document metadata and dense vector matrix to disk."""
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)

        metadata = [doc.model_dump(mode="json") for doc in self._documents]
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump({"documents": metadata, "dim": self.encoder.dim}, f, indent=2)

        np.save(out_dir / "vectors.npy", self._vectors)
        if self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(out_dir / "index.faiss"))
        return out_dir

    @classmethod
    def load_index(
        cls,
        directory: str | Path,
        registry: CanonicalEntityRegistry | None = None,
        encoder: EmbeddingBackend | None = None,
    ) -> SemanticVectorStore:
        """Restore a persisted SemanticVectorStore from disk."""
        in_dir = Path(directory)
        meta_path = in_dir / "metadata.json"
        vec_path = in_dir / "vectors.npy"
        if not meta_path.exists() or not vec_path.exists():
            raise FileNotFoundError(f"Persisted vector store artifacts not found in {in_dir}")

        with open(meta_path, encoding="utf-8") as f:
            payload = json.load(f)

        store = cls(registry=registry, encoder=encoder, load_default_corpus=False)
        docs = [EvidenceItem.model_validate(item) for item in payload.get("documents", [])]
        vectors = np.load(vec_path).astype(np.float32)

        for doc in docs:
            for eid in doc.entity_ids:
                if not store.registry.validate_id(eid):
                    raise ValueError(f"Loaded vector document references ungrounded entity '{eid}'.")

        store._documents = docs
        store._vectors = vectors
        if store._faiss_index is not None:
            faiss_file = in_dir / "index.faiss"
            if faiss_file.exists():
                store._faiss_index = faiss.read_index(str(faiss_file))
            elif vectors.shape[0] > 0:
                store._faiss_index.add(vectors)
        return store

    def _load_corpus(self, corpus_path: str | Path | None = None) -> None:
        """Load initial tagged playbook and disaster analogue corpus."""
        if corpus_path is None:
            candidates = [
                Path(__file__).resolve().parents[3] / "data" / "seeds" / "playbooks_corpus.json",
                Path.cwd() / "data" / "seeds" / "playbooks_corpus.json",
                Path.cwd() / "asci-core" / "data" / "seeds" / "playbooks_corpus.json",
            ]
            corpus_path = next((p for p in candidates if p.exists()), None)

        if corpus_path is not None and Path(corpus_path).exists():
            with open(corpus_path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("documents", []):
                self.add_document(
                    EvidenceItem(
                        citation_id=item["citation_id"],
                        source=item["source"],
                        trust_tier=TrustTier(item["trust_tier"]),
                        entity_ids=item["entity_ids"],
                        snippet=item["snippet"],
                        publication_date=item["publication_date"],
                        supported_claims=item.get("supported_claims", []),
                        region=item.get("region"),
                        hazard_types=[
                            DisruptionEventType(h) for h in item.get("hazard_types", [])
                        ],
                        expires_at=item.get("expires_at"),
                        untrusted_quoted=True,
                    )
                )
        else:
            self._seed_default_playbooks()

    def _seed_default_playbooks(self) -> None:
        """Fallback in-memory seed playbooks when corpus JSON is absent."""
        self.add_document(
            EvidenceItem(
                citation_id="CIT_PLAYBOOK_CYCLONE_001",
                source="IMD & Chennai Port Trust Disaster Standard Operating Procedure",
                trust_tier=TrustTier.TIER_A,
                entity_ids=["PORT_KAMARAJAR", "PORT_CHENNAI", "ICD_TONDIARPET"],
                region="Tamil Nadu",
                hazard_types=[DisruptionEventType.HAZARD_PORT, DisruptionEventType.HAZARD_ROAD],
                snippet=(
                    "In the event of severe cyclonic weather or storm surges impacting Kamarajar Port (Ennore), "
                    "berth operations suspend within 6 hours. Divert inbound containerized auto components to "
                    "Chennai Port CFS Madhavaram or shift long-distance inland cargo to CONCOR Tondiarpet railhead."
                ),
                publication_date="2026-08-15",
                supported_claims=[
                    "Kamarajar Port operations suspend under cyclonic storm warning.",
                    "Chennai Port and ICD Tondiarpet serve as secondary road/rail diversion nodes.",
                ],
                relevance_score=0.95,
            )
        )

    def __len__(self) -> int:
        return len(self._documents)
