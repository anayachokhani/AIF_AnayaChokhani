import csv
from pathlib import Path

import pytest

from formaos.agents.designer import DesignerOutput, DesignerValidationError, design_slots
from formaos.agents.pipeline import PlannerDesignerResult, run_planner_designer
from formaos.agents.planner import PlannerNeed, PlannerOutput, RoomFacts
from formaos.room_state import brief_dimensions_cm, create_room_brief


def planner_output_for(brief, needs: list[PlannerNeed]) -> PlannerOutput:
    dims = brief_dimensions_cm(brief)
    return PlannerOutput(
        room_facts=RoomFacts(
            room_type=brief.room_type,
            width_cm=dims.width_cm,
            depth_cm=dims.depth_cm,
            budget_inr=brief.budget_inr,
            style_words=brief.style_words,
        ),
        constraints=brief.constraints,
        needs_list=needs,
        missing_questions=[],
    )


def need(category: str, share: float, priority: int = 1) -> PlannerNeed:
    return PlannerNeed(
        category=category,
        purpose=f"{category} for the room",
        quantity=1,
        priority=priority,
        max_width_cm=220,
        max_depth_cm=120,
        budget_share=share,
        style_tags=["warm", "wood"],
        constraints=["kid-friendly"],
    )


def write_catalogue(path: Path, categories: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "normalized_category"])
        writer.writeheader()
        for index, category in enumerate(categories):
            writer.writerow({"item_id": f"item-{index}", "normalized_category": category})


def test_living_room_planner_output_becomes_four_to_seven_slots() -> None:
    brief = create_room_brief(
        room_type="living room",
        width=9,
        depth=11,
        units="ft",
        budget_inr=60000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    planner = planner_output_for(brief, [need("sofa", 0.42), need("table", 0.18, 2), need("rug", 0.12, 3)])
    output = design_slots(brief, planner)
    assert 4 <= len(output.slots) <= 7
    assert [slot.category for slot in output.slots][:3] == ["sofa", "table", "rug"]
    assert "storage" in [slot.category for slot in output.slots]
    assert output.concept_image_prompt is None
    for slot in output.slots:
        assert slot.slot_id.startswith("slot_")
        assert slot.target_width_cm is not None and slot.target_width_cm > 0
        assert slot.target_depth_cm is not None and slot.target_depth_cm > 0
        assert slot.style_text
        assert slot.budget_share > 0
        assert slot.placement_hint is not None
    assert 0.98 <= sum(slot.budget_share for slot in output.slots) <= 1.02


def test_tiny_bedroom_gets_compact_valid_slots() -> None:
    brief = create_room_brief(
        room_type="bedroom",
        width=2.5,
        depth=3.0,
        units="m",
        budget_inr=70000,
        style_words=["calm", "compact"],
        constraints=["storage"],
    )
    planner = planner_output_for(brief, [need("bed", 0.55), need("storage", 0.25, 2)])
    output = design_slots(brief, planner)
    assert 4 <= len(output.slots) <= 7
    bed = next(slot for slot in output.slots if slot.category == "bed")
    assert bed.target_width_cm <= 212.5
    assert bed.target_depth_cm <= 220
    assert "lamp" in [slot.category for slot in output.slots]


def test_optional_concept_prompt_is_generated_without_image_spend() -> None:
    brief = create_room_brief(room_type="study", width=8, depth=10, units="ft", budget_inr=60000, style_words=["minimal"])
    planner = planner_output_for(brief, [need("desk", 0.45), need("chair", 0.25, 2), need("lamp", 0.1, 3)])
    output = design_slots(brief, planner, include_concept_prompt=True)
    assert output.concept_image_prompt is not None
    assert "study" in output.concept_image_prompt
    assert "desk" in output.concept_image_prompt
    assert 4 <= len(output.slots) <= 7


def test_study_room_generates_desk_chair_storage_lamp_slots() -> None:
    brief = create_room_brief(room_type="study", width=8, depth=10, units="ft", budget_inr=60000, style_words=["focused"])
    planner = planner_output_for(brief, [need("desk", 0.45), need("chair", 0.25, 2)])
    output = design_slots(brief, planner)
    categories = [slot.category for slot in output.slots]
    assert categories == ["desk", "chair", "storage", "lamp"]
    assert isinstance(output, DesignerOutput)


def test_designer_rejects_slot_category_not_in_curated_catalogue(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalogue.csv"
    write_catalogue(catalogue, ["sofa", "table", "rug"])
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    planner = planner_output_for(brief, [need("sofa", 0.5), need("table", 0.2), need("rug", 0.1), need("lamp", 0.1)])
    with pytest.raises(DesignerValidationError, match="lamp"):
        design_slots(brief, planner, catalogue_path=catalogue)
    try:
        design_slots(brief, planner, catalogue_path=catalogue)
    except DesignerValidationError as exc:
        assert exc.code == "designer_validation_failed"


def test_designer_limits_to_seven_slots_and_normalizes_budget() -> None:
    brief = create_room_brief(room_type="living room", width=12, depth=14, units="ft", budget_inr=120000)
    categories = ["sofa", "table", "rug", "storage", "lamp", "chair", "mirror", "planter"]
    planner = planner_output_for(brief, [need(category, 0.2, min(index + 1, 5)) for index, category in enumerate(categories)])
    output = design_slots(brief, planner)
    assert len(output.slots) == 7
    assert "planter" not in [slot.category for slot in output.slots]
    assert sum(slot.budget_share for slot in output.slots) == pytest.approx(1.0, abs=0.01)


def test_large_room_generates_realistic_footprints_and_valid_budget_sum() -> None:
    brief = create_room_brief(room_type="living room", width=18, depth=22, units="ft", budget_inr=200000)
    planner = planner_output_for(
        brief,
        [need("sofa", 0.35), need("table", 0.15, 2), need("rug", 0.15, 3), need("storage", 0.2, 4), need("lamp", 0.05, 5)],
    )
    output = design_slots(brief, planner)
    assert len(output.slots) == 5
    sofa = next(slot for slot in output.slots if slot.category == "sofa")
    rug = next(slot for slot in output.slots if slot.category == "rug")
    assert sofa.target_width_cm <= 230
    assert sofa.target_depth_cm <= 105
    assert rug.target_width_cm <= 300
    assert rug.target_depth_cm <= 300
    assert sum(slot.budget_share for slot in output.slots) == pytest.approx(1.0, abs=0.01)


def test_invalid_planner_output_payload_raises_typed_designer_error() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    malformed_payload = {"room_facts": {"room_type": "living_room"}, "needs_list": []}
    with pytest.raises(DesignerValidationError) as exc_info:
        design_slots(brief, malformed_payload)
    assert exc_info.value.code == "designer_validation_failed"
    assert exc_info.value.original_error is not None


def test_missing_required_planner_need_fields_raise_typed_error() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    dims = brief_dimensions_cm(brief)
    incomplete_payload = {
        "room_facts": {
            "room_type": brief.room_type,
            "width_cm": dims.width_cm,
            "depth_cm": dims.depth_cm,
            "budget_inr": brief.budget_inr,
            "style_words": brief.style_words,
        },
        "constraints": brief.constraints,
        "needs_list": [{"category": "sofa"}],
        "missing_questions": [],
    }
    with pytest.raises(DesignerValidationError) as exc_info:
        design_slots(brief, incomplete_payload)
    assert exc_info.value.code == "designer_validation_failed"


def test_invalid_category_payload_raises_typed_designer_error() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    dims = brief_dimensions_cm(brief)
    payload = {
        "room_facts": {
            "room_type": brief.room_type,
            "width_cm": dims.width_cm,
            "depth_cm": dims.depth_cm,
            "budget_inr": brief.budget_inr,
            "style_words": brief.style_words,
        },
        "constraints": brief.constraints,
        "needs_list": [
            {
                "category": "imaginary",
                "purpose": "invalid object",
                "quantity": 1,
                "priority": 1,
                "budget_share": 0.5,
            },
            {
                "category": "sofa",
                "purpose": "seating",
                "quantity": 1,
                "priority": 2,
                "budget_share": 0.5,
            },
        ],
        "missing_questions": [],
    }
    with pytest.raises(DesignerValidationError) as exc_info:
        design_slots(brief, payload)
    assert exc_info.value.code == "designer_validation_failed"


def test_planner_output_must_preserve_room_brief_fields() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000, style_words=["warm"])
    planner = planner_output_for(brief, [need("sofa", 0.5), need("table", 0.2)])
    payload = planner.model_dump()
    payload["room_facts"]["budget_inr"] = 1
    with pytest.raises(DesignerValidationError, match="budget"):
        design_slots(brief, payload)


class FakePipelinePlannerClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages: list[dict[str, str]]) -> str:
        import json

        return json.dumps(self.payload)


def test_planner_designer_pipeline_uses_designer_and_preserves_brief() -> None:
    brief = create_room_brief(
        room_type="living room",
        width=9,
        depth=11,
        units="ft",
        budget_inr=60000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    planner = planner_output_for(brief, [need("sofa", 0.42), need("table", 0.18, 2), need("rug", 0.12, 3)])
    result = run_planner_designer(brief, planner_client=FakePipelinePlannerClient(planner.model_dump()), include_concept_prompt=True)
    assert isinstance(result, PlannerDesignerResult)
    assert result.planner_output.room_facts.room_type == brief.room_type
    assert result.planner_output.room_facts.budget_inr == brief.budget_inr
    assert 4 <= len(result.designer_output.slots) <= 7
    assert result.designer_output.concept_image_prompt is not None
    assert all(slot.must_have_constraints for slot in result.designer_output.slots)
