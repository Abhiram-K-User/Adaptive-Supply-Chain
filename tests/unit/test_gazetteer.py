"""
Unit tests for upgraded multi-entity, fuzzy, and geospatial Gazetteer resolution.
"""

from asci.core.registry import CanonicalEntityRegistry


def test_multi_entity_extraction(registry: CanonicalEntityRegistry):
    """Verify multiple canonical entities are extracted from an article headline & body."""
    text = (
        "Cyclone Michaung forces berth closure at Ennore Port; "
        "Chennai Port and Oragadam auto plants activate CONCOR Bengaluru rail bypass."
    )
    matches = registry.resolve_entities(text)
    matched_ids = [m.entity.id for m in matches]

    assert "PORT_KAMARAJAR" in matched_ids
    assert "PORT_CHENNAI" in matched_ids
    assert "PLANT_ORAGADAM" in matched_ids
    assert "ICD_WHITEFIELD" in matched_ids


def test_fuzzy_gazetteer_typos(registry: CanonicalEntityRegistry):
    """Verify fuzzy matching handles minor typos in logistics news reports."""
    matches = registry.resolve_entities("Operations slowed at Kamrajar port and Oragdam cluster", min_score=0.78)
    matched_ids = {m.entity.id for m in matches}

    assert "PORT_KAMARAJAR" in matched_ids
    assert "PLANT_ORAGADAM" in matched_ids


def test_resolution_memory_cache(registry: CanonicalEntityRegistry):
    """Verify surface-form resolution memory speeds up and stores custom aliases."""
    registry.record_resolution("Ennore Automotive Gate", "PORT_KAMARAJAR")
    resolved = registry.resolve_name("Ennore Automotive Gate")
    assert resolved is not None
    assert resolved.id == "PORT_KAMARAJAR"


def test_geospatial_coordinate_resolution(registry: CanonicalEntityRegistry):
    """Verify Haversine proximity resolution around Ennore / Chennai coastal cluster."""
    # Coordinates right near PORT_KAMARAJAR (13.2611, 80.3314)
    matches = registry.resolve_by_coordinates(lat=13.26, lon=80.33, radius_km=30.0)
    matched_ids = [m.entity.id for m in matches]

    assert len(matches) >= 3
    assert matched_ids[0] == "PORT_KAMARAJAR"
    assert "PORT_KATTUPALLI" in matched_ids
    assert "CFS_ENNORE_LOGISTICS" in matched_ids
    assert "PORT_CHENNAI" in matched_ids
    assert "PORT_COCHIN" not in matched_ids


def test_geospatial_polygon_intersection(registry: CanonicalEntityRegistry):
    """Verify GDACS-style polygon intersection captures enclosed coastal hubs."""
    # Polygon bounding Chennai-Ennore-Kattupalli coast (lat, lon)
    coastal_box = [
        (12.95, 80.10),
        (12.95, 80.45),
        (13.45, 80.45),
        (13.45, 80.10),
    ]
    matches = registry.resolve_by_polygon(coastal_box, buffer_km=5.0)
    matched_ids = {m.entity.id for m in matches}

    assert "PORT_KAMARAJAR" in matched_ids
    assert "PORT_KATTUPALLI" in matched_ids
    assert "PORT_CHENNAI" in matched_ids
    assert "CFS_ENNORE_LOGISTICS" in matched_ids
    assert "PLANT_HOSUR" not in matched_ids

