"""
Unit tests for Canonical Entity Registry.
Verifies identifier grounding, gazetteer resolution, and unknown entity validation.
"""

import pytest
from pydantic import ValidationError

from asci.core.registry import CanonicalEntityRegistry, EntityType, UnknownEntityError


def test_registry_loading(registry: CanonicalEntityRegistry):
    """Verify registry loads all seed entities and count is non-zero."""
    assert len(registry) >= 15
    entities = registry.all_entities()
    assert "PORT_CHENNAI" in entities
    assert "PORT_KAMARAJAR" in entities
    assert "PLANT_ORAGADAM" in entities
    assert "PLANT_SRIPERUMBUDUR" in entities


def test_canonical_id_validation(registry: CanonicalEntityRegistry):
    """Verify validate_id correctly distinguishes valid and invalid IDs."""
    assert registry.validate_id("PORT_CHENNAI") is True
    assert registry.validate_id("PLANT_ORAGADAM") is True
    assert registry.validate_id("ICD_WHITEFIELD") is True

    # Ungrounded entities must fail
    assert registry.validate_id("PORT_ROTTERDAM") is False
    assert registry.validate_id("UNKNOWN_HUB_999") is False
    assert registry.validate_id("") is False


def test_entity_get_and_unknown_rejection(registry: CanonicalEntityRegistry):
    """Verify get returns Entity or raises UnknownEntityError."""
    entity = registry.get("PORT_KAMARAJAR")
    assert entity.id == "PORT_KAMARAJAR"
    assert entity.entity_type == EntityType.PORT
    assert entity.region == "Tamil Nadu"

    with pytest.raises(UnknownEntityError):
        registry.get("NON_EXISTENT_ENTITY")


def test_gazetteer_resolution(registry: CanonicalEntityRegistry):
    """Verify unstructured text and aliases resolve to canonical IDs."""
    # Exact and alias matches
    res1 = registry.resolve_name("Ennore Port")
    assert res1 is not None
    assert res1.id == "PORT_KAMARAJAR"

    res2 = registry.resolve_name("Chennai Harbour")
    assert res2 is not None
    assert res2.id == "PORT_CHENNAI"

    res3 = registry.resolve_name("Renault Nissan Oragadam")
    assert res3 is not None
    assert res3.id == "PLANT_ORAGADAM"

    res4 = registry.resolve_name("Toyota Bidadi")
    assert res4 is not None
    assert res4.id == "PLANT_BIDADI"

    res5 = registry.resolve_name("Completely unrelated text without entity")
    assert res5 is None


def test_filter_by_type(registry: CanonicalEntityRegistry):
    """Verify entity retrieval by EntityType."""
    ports = registry.get_by_type(EntityType.PORT)
    assert len(ports) >= 6
    port_ids = {p.id for p in ports}
    assert "PORT_CHENNAI" in port_ids
    assert "PORT_KAMARAJAR" in port_ids
    assert "PORT_COCHIN" in port_ids

    plants = registry.get_by_type(EntityType.PLANT)
    assert len(plants) >= 5
    plant_ids = {p.id for p in plants}
    assert "PLANT_ORAGADAM" in plant_ids
    assert "PLANT_SRIPERUMBUDUR" in plant_ids
    assert "PLANT_HOSUR" in plant_ids


def test_entity_immutability(registry: CanonicalEntityRegistry):
    """Verify that Entity models are frozen and immutable."""
    entity = registry.get("PORT_CHENNAI")
    with pytest.raises(ValidationError):
        entity.name = "Modified Name"  # type: ignore

