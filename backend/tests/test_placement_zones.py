from __future__ import annotations

import pytest
from pydantic import ValidationError

from formaos.contracts import DesignSlot
from formaos.placement.zones import (
    PlacementZoneError,
    ZONES,
    assign_zone_for_slot,
    default_zones_for_category,
    is_valid_zone,
    map_placement_hint_to_zone,
    map_user_chip_location,
)


def test_defines_required_three_by_three_zones_in_grid_order() -> None:
    assert ZONES == ("NW", "N", "NE", "W", "C", "E", "SW", "S", "SE")
    assert all(is_valid_zone(zone) for zone in ZONES)


def test_maps_placement_hint_to_single_zone() -> None:
    for zone in ZONES:
        assert map_placement_hint_to_zone(zone) == zone


def test_invalid_placement_hint_raises_typed_error() -> None:
    with pytest.raises(PlacementZoneError) as exc_info:
        map_placement_hint_to_zone("UP")
    assert exc_info.value.code == "placement_zone_validation_failed"

    with pytest.raises(ValidationError):
        DesignSlot(slot_id="slot_bad_zone", category="lamp", budget_share=1.0, placement_hint="UP")


def test_maps_user_chip_location_aliases_to_zones() -> None:
    assert map_user_chip_location("north east") == "NE"
    assert map_user_chip_location("centre") == "C"
    assert map_user_chip_location("SW") == "SW"
    assert map_user_chip_location("unknown") is None


def test_automatic_category_zone_defaults() -> None:
    assert default_zones_for_category("bed") == ("SW",)
    assert default_zones_for_category("wardrobe") == ("SW", "S", "W")
    assert default_zones_for_category("storage") == ("SW", "S", "W")
    assert default_zones_for_category("sofa") == ("S", "W")
    assert default_zones_for_category("mirror") == ("N", "E")
    assert default_zones_for_category("stove") == ("SE",)


def test_slot_zone_assignment_prefers_user_chip_then_hint_then_default() -> None:
    slot = DesignSlot(slot_id="slot_1_sofa", category="sofa", budget_share=0.4, placement_hint="S")
    assert assign_zone_for_slot(slot, user_chip_location="north") == "N"
    assert assign_zone_for_slot(slot) == "S"

    defaulted = DesignSlot(slot_id="slot_2_bed", category="bed", budget_share=0.6)
    assert assign_zone_for_slot(defaulted) == "SW"
