"""
Semantic Vector Memory Stub for Disaster Bulletins & Mitigation Playbooks.
Maintains tagged evidence items linked to Canonical Entity IDs and Trust Tiers.
"""

from __future__ import annotations

import re
from typing import Any

from asci.core.registry import CanonicalEntityRegistry, get_canonical_registry
from asci.core.state import EvidenceItem, TrustTier


class SemanticVectorStore:
    """
    In-memory semantic vector store stub.
    Provides keyword-overlap and semantic matching over curated corridor playbooks.
    """

    def __init__(self, registry: CanonicalEntityRegistry | None = None) -> None:
        self.registry = registry or get_canonical_registry()
        self._documents: list[EvidenceItem] = []
        self._seed_default_playbooks()

    def add_document(self, doc: EvidenceItem) -> None:
        """Index an evidence document after validating referenced entity IDs."""
        for entity_id in doc.entity_ids:
            if not self.registry.validate_id(entity_id):
                raise ValueError(
                    f"Evidence document references ungrounded entity ID '{entity_id}'."
                )
        self._documents.append(doc)

    def query(
        self,
        query_text: str,
        entity_ids: list[str] | None = None,
        min_trust_tier: TrustTier | None = None,
        limit: int = 5,
    ) -> list[EvidenceItem]:
        """
        Retrieve relevant evidence passages filtered by canonical entity IDs and trust tier.
        Scores relevance based on query token intersection and entity grounding.
        """
        query_tokens = set(re.findall(r"\w+", query_text.lower()))
        results: list[tuple[float, EvidenceItem]] = []

        tier_order = {TrustTier.TIER_A: 3, TrustTier.TIER_B: 2, TrustTier.TIER_C: 1}
        min_rank = tier_order.get(min_trust_tier, 0) if min_trust_tier else 0

        for doc in self._documents:
            # Filter by trust tier rank
            if tier_order.get(doc.trust_tier, 0) < min_rank:
                continue

            # Check entity match if specified
            entity_match = False
            if entity_ids:
                if any(eid in doc.entity_ids for eid in entity_ids):
                    entity_match = True
            else:
                entity_match = True

            if not entity_match:
                continue

            # Compute token overlap score
            doc_tokens = set(re.findall(r"\w+", doc.snippet.lower()))
            intersection = query_tokens.intersection(doc_tokens)
            base_score = len(intersection) / max(len(query_tokens), 1)

            # Boost score if entity directly referenced
            boost = 0.3 if entity_match else 0.0
            score = min(1.0, round(base_score + boost, 3))

            results.append((score, doc))

        # Sort descending by score
        results.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in results[:limit]]

    def _seed_default_playbooks(self) -> None:
        """Seed initial high-trust playbooks for the South India corridor."""
        self.add_document(
            EvidenceItem(
                citation_id="CIT_PLAYBOOK_CYCLONE_001",
                source="IMD & Chennai Port Trust Disaster Standard Operating Procedure",
                trust_tier=TrustTier.TIER_A,
                entity_ids=["PORT_KAMARAJAR", "PORT_CHENNAI", "ICD_TONDIARPET"],
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
        self.add_document(
            EvidenceItem(
                citation_id="CIT_PLAYBOOK_ORAGADAM_002",
                source="Society of Indian Automobile Manufacturers (SIAM) Logistics Advisory",
                trust_tier=TrustTier.TIER_A,
                entity_ids=["PLANT_ORAGADAM", "PLANT_SRIPERUMBUDUR", "ICD_WHITEFIELD"],
                snippet=(
                    "Sriperumbudur and Oragadam automotive assembly hubs maintain 3.5 to 4.5 days of component cover. "
                    "During eastern coastal port stoppages exceeding 48 hours, activate intermodal rail bypass via "
                    "ICD Whitefield or divert shipments to Krishnapatnam Port to prevent assembly line stoppage."
                ),
                publication_date="2026-09-01",
                supported_claims=[
                    "Oragadam cluster requires 48-hour rerouting activation to prevent line stoppage.",
                    "ICD Whitefield and Krishnapatnam provide primary redundancy buffers.",
                ],
                relevance_score=0.90,
            )
        )
        self.add_document(
            EvidenceItem(
                citation_id="CIT_TRADE_PRESS_003",
                source="Hindu BusinessLine Logistics Bureau",
                trust_tier=TrustTier.TIER_B,
                entity_ids=["PORT_KAMARAJAR", "CFS_ENNORE_LOGISTICS"],
                snippet=(
                    "Ennore Express freight highway experiences localized waterlogging during northeast monsoon peak, "
                    "causing average truck turn-around delays of 18 to 24 hours between Ennore CFS and Oragadam."
                ),
                publication_date="2026-10-05",
                supported_claims=[
                    "Ennore freight access routes suffer 18-24 hour transit delays during heavy rainfall.",
                ],
                relevance_score=0.82,
            )
        )

