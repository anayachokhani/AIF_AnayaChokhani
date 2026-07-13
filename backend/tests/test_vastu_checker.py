from __future__ import annotations

from pathlib import Path

import pytest

from formaos.contracts import CatalogueItem
from formaos.room_state import create_room_brief
from formaos.vastu.checker import SEVERITY_WEIGHTS, VastuCheckerError, check_vastu


RULE_PATH = Path("data/vastu/vastu_rules_v1.json")


def item(
    item_id: str,
    product_type: str,
    zone: str | None,
    *,
    title: str | None = None,
    color: str | None = "cream",
    material: str | None = "wood",
) -> CatalogueItem:
    return CatalogueItem(
        item_id=item_id,
        title=title or f"{product_type} item",
        product_type=product_type,
        width_cm=100,
        depth_cm=60,
        height_cm=80,
        material=material,
        color=color,
        price_inr=10000,
        source_dataset="ABO",
        placement_zone=zone,
    )


def test_bedroom_bed_in_ne_and_wardrobe_in_sw_is_deterministic() -> None:
    brief = create_room_brief(room_type="bedroom", width=10, depth=12, units="ft", budget_inr=120000)
    bed = item("bed-1", "bed", "NE", title="Bed in NE", color="cream", material="wood")
    wardrobe = item("wardrobe-1", "wardrobe", "SW", title="Wardrobe in SW", color="earth", material="wood")

    first = check_vastu(brief, [bed, wardrobe], rule_path=RULE_PATH)
    second = check_vastu(brief, [bed, wardrobe], rule_path=RULE_PATH)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert 0 <= first.score <= 100
    assert first.score < 100
    bed_result = next(result for result in first.item_results if result.item_id == "bed-1")
    wardrobe_result = next(result for result in first.item_results if result.item_id == "wardrobe-1")
    assert bed_result.badge == "fail"
    assert any("consider placing" in note for note in bed_result.notes)
    assert wardrobe_result.zone == "SW"
    assert wardrobe_result.object_class == "storage"


def test_checker_computes_pass_warn_fail_per_rule_and_actionable_notes() -> None:
    brief = create_room_brief(room_type="bedroom", width=10, depth=12, units="ft", budget_inr=120000)
    black_bed = item("bed-2", "bed", "S", title="Black bed in south", color="black", material="wood")
    ne_bed = item("bed-3", "bed", "NE", title="Bed in north east", color="cream", material="wood")

    result = check_vastu(brief, [black_bed, ne_bed], rule_path=RULE_PATH)
    statuses = {rule_result.status for item_result in result.item_results for rule_result in item_result.rule_results}

    assert {"pass", "warn", "fail"} <= statuses
    assert any(item_result.badge == "fail" for item_result in result.item_results)
    assert any("move" in note or "avoid" in note for note in result.notes)


def test_severity_weights_map_must_should_nice() -> None:
    assert SEVERITY_WEIGHTS == {"critical": 3, "warn": 2, "info": 1}
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    sofa = item("sofa-1", "sofa", "S", color="earth", material="wood")

    result = check_vastu(brief, [sofa], rule_path=RULE_PATH)

    assert result.total_weight > 0
    assert result.earned_weight > 0
    assert {rule.severity for rule in result.item_results[0].rule_results} <= {"must", "should", "nice"}


def test_score_is_zero_to_hundred_and_penalizes_warns_and_fails() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    aligned = check_vastu(brief, [item("sofa-good", "sofa", "S", color="earth", material="wood")], rule_path=RULE_PATH)
    misaligned = check_vastu(brief, [item("sofa-bad", "sofa", "NE", color="black", material="metal")], rule_path=RULE_PATH)

    assert 0 <= aligned.score <= 100
    assert 0 <= misaligned.score <= 100
    assert aligned.score > misaligned.score


def test_rule_matching_uses_material_when_available() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    wooden_storage = item("storage-1", "storage", "W", color="brown", material="wood")

    result = check_vastu(brief, [wooden_storage], rule_path=RULE_PATH)

    assert any(rule.status == "pass" for item_result in result.item_results for rule in item_result.rule_results)
    assert all("storage-1" == item_result.item_id for item_result in result.item_results)


def test_invalid_item_zone_raises_typed_error() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    invalid = item("bad-zone", "sofa", "S").model_copy(update={"placement_zone": "UP"})

    with pytest.raises(VastuCheckerError) as exc_info:
        check_vastu(brief, [invalid], rule_path=RULE_PATH)

    assert exc_info.value.code == "vastu_checker_validation_failed"


def test_checker_rejects_invalid_inputs() -> None:
    with pytest.raises(VastuCheckerError):
        check_vastu({"room_type": "bedroom"}, [], rule_path=RULE_PATH)
