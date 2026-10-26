"""Regression coverage for category definitions and kitchen planning."""
import pytest

from formaos.agents.designer import design_slots, planner_need_from_default
from formaos.agents.planner import PlannerOutput, build_planner_prompt
from formaos.catalogue.curate_abo_subset import plausible_dimensions, price_for
from formaos.definitions import CATEGORIES, DEFAULT_ROOM_TYPES, ROOM_CATEGORIES, ROOM_DEFAULT_NEEDS
from formaos.room_state import brief_dimensions_cm, create_room_brief, parse_room_brief_text


@pytest.mark.parametrize("room", ROOM_DEFAULT_NEEDS)
@pytest.mark.parametrize("budget", [70000, 150000, 200000])
def test_room_defaults_generate_valid_slots(room, budget):
    brief = create_room_brief(room_type=room, width=18, depth=14, budget_inr=budget)
    dims = brief_dimensions_cm(brief)
    planner = PlannerOutput(
        room_facts=dict(room_type=room, width_cm=dims.width_cm, depth_cm=dims.depth_cm,
                        budget_inr=budget, style_words=brief.style_words),
        needs_list=[planner_need_from_default(entry, brief) for entry in ROOM_DEFAULT_NEEDS[room][:2]],
    )
    output = design_slots(brief, planner, include_concept_prompt=True)
    assert sum(slot.budget_share for slot in output.slots) == pytest.approx(1.0, abs=0.001)
    assert room.replace("_", " ") in output.concept_image_prompt
    for slot in output.slots:
        assert slot.target_width_cm > 0 and slot.target_depth_cm > 0
        assert slot.placement_hint is not None
    if room == "kitchen":
        assert {"refrigerator", "utensil", "basin", "storage"} <= {s.category for s in output.slots}


def test_registry_covers_every_room_and_catalogue_category():
    assert ROOM_CATEGORIES.keys() == DEFAULT_ROOM_TYPES.keys()
    for room, defaults in ROOM_DEFAULT_NEEDS.items():
        assert ROOM_CATEGORIES[room] == [entry["category"] for entry in defaults]
        assert set(ROOM_CATEGORIES[room]) <= CATEGORIES.keys()
    for category, definition in CATEGORIES.items():
        width, depth = definition.footprint(300, 300)
        assert width > 0 and depth > 0
        assert definition.placement in definition.zones
        assert category in definition.terms
        low_w, high_w, low_d, high_d, low_h, high_h = definition.dimension_band
        dimensions = ((low_w + high_w) / 2, (low_d + high_d) / 2, (low_h + high_h) / 2)
        assert plausible_dimensions(category, *dimensions)
        assert price_for(category, *dimensions, "metal") > 0


def test_kitchen_text_and_prompt_use_kitchen_defaults():
    assert parse_room_brief_text("Design my kitchen")['room_type'] == "kitchen"
    messages = build_planner_prompt(create_room_brief(room_type="kitchen"))
    assert '"category": "refrigerator"' in messages[1]['content']
