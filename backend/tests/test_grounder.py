from __future__ import annotations

import csv
from pathlib import Path

import pytest

from formaos.agents.designer import design_slots
from formaos.agents.grounder import (
    GrounderValidationError,
    compute_slot_budget_inr,
    compute_slot_limits,
    ground_design,
)
from formaos.agents.pipeline import PlannerDesignerGrounderResult, run_planner_designer_grounder
from formaos.agents.planner import PlannerNeed, PlannerOutput, RoomFacts
from formaos.catalogue.index_catalogue import build_index
from formaos.contracts import DesignSlot
from formaos.placement.zones import ZONES
from formaos.room_state import brief_dimensions_cm, create_room_brief


CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")
BASE_CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue.csv")


@pytest.fixture(scope="module")
def chroma_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("grounder_chroma")
    summary = build_index(CATALOGUE_PATH, path)
    assert summary["indexed_count"] >= 150
    return path


@pytest.fixture(scope="module")
def catalogue_ids() -> set[str]:
    with BASE_CATALOGUE_PATH.open(newline="", encoding="utf-8") as handle:
        return {row["item_id"] for row in csv.DictReader(handle)}


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
        budget_share=share,
        style_tags=["warm", "wood"],
        constraints=["kid-friendly"],
    )


def assert_grounded_items_pass_filters(grounded, catalogue_ids: set[str]) -> None:
    selected_ids: list[str] = []
    for grounded_slot in grounded.grounded_slots:
        slot = grounded_slot.slot
        selected = grounded_slot.selected_item
        constraints = grounded_slot.constraints
        assert grounded_slot.failure is None
        assert grounded_slot.placement_zone in ZONES
        assert grounded_slot.placement_zone == slot.placement_hint
        assert selected is not None
        assert selected.placement_zone == grounded_slot.placement_zone
        selected_ids.append(selected.item_id)
        assert selected.item_id in catalogue_ids
        assert selected.source_dataset == "ABO"
        assert selected.product_type == slot.category
        assert selected.width_cm <= constraints.max_width_cm
        assert selected.depth_cm <= constraints.max_depth_cm
        assert selected.price_inr <= constraints.max_price_inr
        assert 2 <= len(grounded_slot.alternatives) <= 3
        for alternative in grounded_slot.alternatives:
            assert alternative.item_id in catalogue_ids
            assert alternative.placement_zone == grounded_slot.placement_zone
            assert alternative.product_type == slot.category
            assert alternative.width_cm <= constraints.max_width_cm
            assert alternative.depth_cm <= constraints.max_depth_cm
            assert alternative.price_inr <= constraints.max_price_inr
    assert len(selected_ids) == len(set(selected_ids))


def living_room_slots(brief):
    planner = planner_output_for(
        brief,
        [need("sofa", 0.45), need("table", 0.2, 2), need("rug", 0.2, 3), need("lamp", 0.15, 4)],
    )
    return design_slots(brief, planner).slots


def test_normal_living_room_selects_real_catalogue_items_with_alternatives(
    chroma_path: Path, catalogue_ids: set[str]
) -> None:
    brief = create_room_brief(
        room_type="living room",
        width=12,
        depth=14,
        units="ft",
        budget_inr=140000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    slots = living_room_slots(brief)
    grounded = ground_design(brief, slots, chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    assert not grounded.failures
    assert_grounded_items_pass_filters(grounded, catalogue_ids)


def test_single_valid_catalogue_result_is_selected_without_requiring_alternatives(monkeypatch) -> None:
    brief = create_room_brief(room_type="bedroom", width=9, depth=7, units="ft", budget_inr=245000)
    slot = DesignSlot(
        slot_id="slot_rug",
        category="rug",
        target_width_cm=214,
        target_depth_cm=132.3,
        budget_share=0.08,
        placement_hint="C",
    )
    result = {
        "item_id": "B071777YN3",
        "title": "Hand-woven natural rug",
        "category": "rug",
        "width_cm": 182.9,
        "depth_cm": 121.9,
        "height_cm": 1.0,
        "price_inr": 7100,
        "material": "wool",
        "color": "natural",
        "image_path": "/product-images/B071777YN3-A194kPVvFmL.jpg",
        "image_available": True,
    }
    monkeypatch.setattr("formaos.agents.grounder.search_items", lambda *_args, **_kwargs: [result])

    grounded = ground_design(brief, [slot], catalogue_path=CATALOGUE_PATH)

    assert not grounded.failures
    assert grounded.grounded_slots[0].selected_item.item_id == "B071777YN3"
    assert grounded.grounded_slots[0].alternatives == []


def test_bedroom_storage_prefers_actual_storage_furniture(chroma_path: Path) -> None:
    brief = create_room_brief(
        room_type="bedroom",
        width=14,
        depth=16,
        units="ft",
        budget_inr=240000,
        style_words=["japandi"],
    )
    slot = DesignSlot(
        slot_id="slot_bedroom_storage",
        category="storage",
        target_width_cm=160,
        target_depth_cm=65,
        style_text="japandi wardrobe or drawer storage",
        budget_share=0.3,
        placement_hint="W",
    )

    grounded = ground_design(brief, [slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    selected = grounded.grounded_slots[0].selected_item

    assert selected is not None
    title = selected.title.lower()
    assert any(term in title for term in ["drawer", "organizer", "shelf", "cabinet", "wardrobe", "dresser"])
    assert not any(term in title for term in ["coffee table", "ottoman", "bench", "desk", "container", "recliner"])


def test_small_room_returns_structured_failures_for_items_that_do_not_fit(chroma_path: Path) -> None:
    brief = create_room_brief(
        room_type="living room",
        width=5,
        depth=6,
        units="ft",
        budget_inr=140000,
        style_words=["compact"],
        constraints=["kids play here"],
    )
    slots = living_room_slots(brief)
    grounded = ground_design(brief, slots, chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)

    assert grounded.failures
    assert {failure.blocked_by for failure in grounded.failures} <= {
        "maximum_width_exceeded",
        "maximum_depth_exceeded",
        "dimension_combination_exceeded",
        "no_catalogue_match",
    }


def test_large_room_keeps_items_within_slot_maximums(chroma_path: Path, catalogue_ids: set[str]) -> None:
    brief = create_room_brief(room_type="living room", width=18, depth=22, units="ft", budget_inr=220000)
    slots = living_room_slots(brief)
    grounded = ground_design(brief, slots, chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)

    assert not grounded.failures
    assert_grounded_items_pass_filters(grounded, catalogue_ids)


def test_slot_budget_comes_from_total_budget_and_share() -> None:
    brief = create_room_brief(room_type="study", width=8, depth=10, units="ft", budget_inr=80000)
    slot = DesignSlot(slot_id="slot_1_desk", category="desk", budget_share=0.25)
    assert compute_slot_budget_inr(brief, slot) == 20000


def test_placement_hint_changes_dimension_limits() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=100000)
    center_slot = DesignSlot(slot_id="slot_table", category="table", budget_share=0.5, placement_hint="C")
    wall_slot = DesignSlot(slot_id="slot_storage", category="storage", budget_share=0.5, placement_hint="W")

    center_limits = compute_slot_limits(brief, center_slot)
    wall_limits = compute_slot_limits(brief, wall_slot)

    assert center_limits.max_width_cm > wall_limits.max_width_cm
    assert wall_limits.max_depth_cm > center_limits.max_depth_cm


def test_room_constraints_reduce_dimension_limits() -> None:
    open_brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=100000)
    constrained_brief = create_room_brief(
        room_type="living room",
        width=10,
        depth=12,
        units="ft",
        budget_inr=100000,
        constraints=["kids play here"],
    )
    slot = DesignSlot(slot_id="slot_table", category="table", budget_share=0.5, placement_hint="C")

    open_limits = compute_slot_limits(open_brief, slot)
    constrained_limits = compute_slot_limits(constrained_brief, slot)

    assert constrained_limits.max_width_cm == pytest.approx(open_limits.max_width_cm * 0.9, abs=0.1)
    assert constrained_limits.max_depth_cm == pytest.approx(open_limits.max_depth_cm * 0.9, abs=0.1)


def test_oversized_furniture_returns_width_failure(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    impossible_slot = DesignSlot(
        slot_id="slot_impossible_sofa",
        category="sofa",
        target_width_cm=1,
        target_depth_cm=1,
        budget_share=0.5,
        style_text="warm sofa",
        placement_hint="C",
    )

    grounded = ground_design(brief, [impossible_slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    grounded_slot = grounded.grounded_slots[0]

    assert grounded_slot.selected_item is None
    assert grounded_slot.alternatives == []
    assert grounded_slot.failure is not None
    assert grounded_slot.placement_zone == "C"
    assert grounded_slot.failure.code == "width"
    assert grounded_slot.failure.blocked_by == "maximum_width_exceeded"
    assert "blocked by maximum_width_exceeded" in grounded_slot.failure.message


def test_budget_failure_identifies_price_constraint(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=12, depth=14, units="ft", budget_inr=100)
    sofa_slot = DesignSlot(
        slot_id="slot_low_budget_sofa",
        category="sofa",
        target_width_cm=240,
        target_depth_cm=110,
        budget_share=1.0,
        style_text="warm sofa",
        placement_hint="C",
    )

    grounded = ground_design(brief, [sofa_slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    failure = grounded.grounded_slots[0].failure

    assert failure is not None
    assert grounded.grounded_slots[0].placement_zone == "C"
    assert failure.code == "budget"
    assert failure.blocked_by == "budget_exceeded"


def test_room_too_shallow_returns_depth_failure(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    shallow_slot = DesignSlot(
        slot_id="slot_shallow_sofa",
        category="sofa",
        target_width_cm=240,
        target_depth_cm=1,
        budget_share=1.0,
        style_text="warm sofa",
        placement_hint="C",
    )

    grounded = ground_design(brief, [shallow_slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    failure = grounded.grounded_slots[0].failure

    assert failure is not None
    assert failure.code == "depth"
    assert failure.blocked_by == "maximum_depth_exceeded"


def test_missing_category_returns_category_failure(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=12, depth=14, units="ft", budget_inr=100000)
    slot = DesignSlot(
        slot_id="slot_missing_category",
        category="sideboard",
        target_width_cm=100,
        target_depth_cm=40,
        budget_share=0.5,
        placement_hint="W",
    )

    grounded = ground_design(brief, [slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    failure = grounded.grounded_slots[0].failure

    assert failure is not None
    assert failure.code == "category"
    assert failure.blocked_by == "category_unavailable"


def test_tight_budget_returns_structured_no_result_response(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="study", width=8, depth=10, units="ft", budget_inr=50)
    slot = DesignSlot(
        slot_id="slot_low_budget_lamp",
        category="lamp",
        target_width_cm=100,
        target_depth_cm=100,
        budget_share=1.0,
        placement_hint="C",
    )

    grounded = ground_design(brief, [slot], chroma_path=chroma_path, catalogue_path=CATALOGUE_PATH)
    failure = grounded.grounded_slots[0].failure

    assert failure is not None
    assert failure.blocked_by == "budget_exceeded"
    assert failure.constraints.max_price_inr == 50
    assert failure.query == "lamp"


def test_invalid_design_slot_raises_typed_error(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    with pytest.raises(GrounderValidationError) as exc_info:
        ground_design(brief, [{"slot_id": "bad", "category": "sofa"}], chroma_path=chroma_path)

    assert exc_info.value.code == "grounder_validation_failed"


def test_invalid_room_brief_raises_typed_error(chroma_path: Path) -> None:
    slot = DesignSlot(slot_id="slot_1_lamp", category="lamp", budget_share=1.0)
    invalid_brief = {"room_type": "study", "width": 8, "depth": 10, "units": "ft"}

    with pytest.raises(GrounderValidationError) as exc_info:
        ground_design(invalid_brief, [slot], chroma_path=chroma_path)

    assert exc_info.value.code == "grounder_validation_failed"


def test_invalid_placement_hint_raises_typed_error(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    invalid_slot = {"slot_id": "slot_bad_hint", "category": "lamp", "budget_share": 1.0, "placement_hint": "UP"}

    with pytest.raises(GrounderValidationError):
        ground_design(brief, [invalid_slot], chroma_path=chroma_path)


def test_grounder_rejects_invalid_existing_slot_zone_assignment(chroma_path: Path) -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    slot = DesignSlot(slot_id="slot_lamp", category="lamp", budget_share=1.0)
    invalid_slot = slot.model_copy(update={"placement_hint": "UP"})

    with pytest.raises(GrounderValidationError) as exc_info:
        ground_design(brief, [invalid_slot], chroma_path=chroma_path)

    assert exc_info.value.code == "grounder_validation_failed"
    assert exc_info.value.original_error is not None


def test_invalid_budget_raises_typed_error(chroma_path: Path) -> None:
    slot = DesignSlot(slot_id="slot_1_lamp", category="lamp", budget_share=1.0)
    invalid_brief = {"room_type": "study", "width": 8, "depth": 10, "units": "ft", "budget_inr": 0}

    with pytest.raises(GrounderValidationError):
        ground_design(invalid_brief, [slot], chroma_path=chroma_path)


def test_invalid_dimensions_raise_typed_error(chroma_path: Path) -> None:
    slot = DesignSlot(slot_id="slot_1_lamp", category="lamp", budget_share=1.0)
    invalid_brief = {"room_type": "study", "width": -8, "depth": 10, "units": "ft", "budget_inr": 50000}

    with pytest.raises(GrounderValidationError):
        ground_design(invalid_brief, [slot], chroma_path=chroma_path)


def test_grounder_passes_hard_filters_to_chroma_search(monkeypatch: pytest.MonkeyPatch, catalogue_ids: set[str]) -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=90000)
    slot = DesignSlot(
        slot_id="slot_lamp",
        category="lamp",
        target_width_cm=60,
        target_depth_cm=60,
        budget_share=0.5,
        style_text="warm lamp",
        placement_hint="C",
    )
    captured: dict[str, object] = {}

    def fake_search_items(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return [
            {
                "item_id": "B07M6PHM8C",
                "title": "Lamp A",
                "category": "lamp",
                "width_cm": 35.0,
                "depth_cm": 35.0,
                "height_cm": 150.0,
                "price_inr": 7000,
                "material": "metal",
                "color": "black",
                "image_path": "/product-images/lamp-a.jpg",
                "image_available": True,
            },
            {
                "item_id": "B07HK85JKQ",
                "title": "Lamp B",
                "category": "lamp",
                "width_cm": 40.0,
                "depth_cm": 40.0,
                "height_cm": 140.0,
                "price_inr": 8000,
                "material": "metal",
                "color": "white",
                "image_path": "/product-images/lamp-b.jpg",
                "image_available": True,
            },
            {
                "item_id": "B07DT4GYTD",
                "title": "Lamp C",
                "category": "lamp",
                "width_cm": 45.0,
                "depth_cm": 45.0,
                "height_cm": 130.0,
                "price_inr": 9000,
                "material": "wood",
                "color": "brown",
                "image_path": "/product-images/lamp-c.jpg",
                "image_available": True,
            },
        ]

    monkeypatch.setattr("formaos.agents.grounder.search_items", fake_search_items)

    grounded = ground_design(brief, [slot], catalogue_path=CATALOGUE_PATH)

    assert captured["category"] == "lamp"
    assert captured["max_width_cm"] == 60
    assert captured["max_depth_cm"] == 60
    assert captured["max_price_inr"] == 45000
    assert grounded.grounded_slots[0].selected_item is not None
    assert grounded.grounded_slots[0].selected_item.item_id in catalogue_ids
    assert grounded.grounded_slots[0].placement_zone == "C"


class FakePlannerClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages: list[dict[str, str]]) -> str:
        import json

        return json.dumps(self.payload)


def test_planner_designer_grounder_pipeline_integration(chroma_path: Path, catalogue_ids: set[str]) -> None:
    brief = create_room_brief(
        room_type="living room",
        width=12,
        depth=14,
        units="ft",
        budget_inr=140000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    planner = planner_output_for(
        brief,
        [need("sofa", 0.45), need("table", 0.2, 2), need("rug", 0.2, 3), need("lamp", 0.15, 4)],
    )

    result = run_planner_designer_grounder(
        brief,
        planner_client=FakePlannerClient(planner.model_dump()),
        catalogue_path=CATALOGUE_PATH,
        chroma_path=chroma_path,
    )

    assert isinstance(result, PlannerDesignerGrounderResult)
    assert [slot.slot_id for slot in result.designer_output.slots] == [
        grounded.slot.slot_id for grounded in result.grounder_output.grounded_slots
    ]
    for designer_slot, grounded_slot in zip(result.designer_output.slots, result.grounder_output.grounded_slots):
        assert grounded_slot.slot.placement_hint == designer_slot.placement_hint
        assert grounded_slot.placement_zone == designer_slot.placement_hint
        assert grounded_slot.placement_zone in ZONES
        assert grounded_slot.placement_zone
        assert grounded_slot.selected_item is not None
        assert grounded_slot.selected_item.placement_zone == grounded_slot.placement_zone
        assert all(alternative.placement_zone == grounded_slot.placement_zone for alternative in grounded_slot.alternatives)
    assert not result.grounder_output.failures
    assert_grounded_items_pass_filters(result.grounder_output, catalogue_ids)
