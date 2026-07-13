import pytest
from pydantic import ValidationError

from formaos.contracts import RoomBrief
from formaos.room_state import (
    InMemoryStateStore,
    brief_dimensions_cm,
    create_initial_state,
    create_room_brief,
    parse_room_brief_text,
    to_graph_state,
)


def test_room_brief_requires_budget() -> None:
    with pytest.raises(ValidationError):
        RoomBrief(room_type="living_room", width=10, depth=12, units="ft")


def test_invalid_dimensions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RoomBrief(room_type="living_room", width=0, depth=12, units="ft", budget_inr=85000)


def test_feet_convert_to_centimeters() -> None:
    brief = RoomBrief(room_type="living_room", width=10, depth=12, units="ft", budget_inr=85000)
    dims = brief_dimensions_cm(brief)
    assert dims.width_cm == 304.8
    assert dims.depth_cm == 365.8


def test_meters_convert_to_centimeters() -> None:
    brief = RoomBrief(room_type="study", width=3.2, depth=4.1, units="m", budget_inr=50000)
    dims = brief_dimensions_cm(brief)
    assert dims.width_cm == 320.0
    assert dims.depth_cm == 410.0


def test_centimeters_remain_centimeters() -> None:
    brief = RoomBrief(room_type="study", width=320, depth=410, units="cm", budget_inr=50000)
    dims = brief_dimensions_cm(brief)
    assert dims.width_cm == 320.0
    assert dims.depth_cm == 410.0


def test_partial_brief_gets_living_room_defaults() -> None:
    brief = create_room_brief(style_words="warm wood storage", vastu_enabled=True)
    assert brief.room_type == "living_room"
    assert brief.width == 10
    assert brief.depth == 12
    assert brief.budget_inr == 85000
    assert brief.style_words == ["warm", "wood", "storage"]
    assert brief.vastu_enabled is True


def test_partial_bedroom_brief_gets_bedroom_defaults() -> None:
    brief = create_room_brief(room_type="bedroom")
    assert brief.room_type == "bedroom"
    assert brief.width == 10
    assert brief.depth == 11
    assert brief.units == "ft"
    assert brief.budget_inr == 90000
    assert brief.style_words == ["calm", "storage"]


def test_initial_state_preserves_brief_and_cm_dimensions() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    state = create_initial_state("test-session", brief)
    assert state.session_id == "test-session"
    assert state.brief == brief
    assert state.brief_cm is not None
    assert state.brief_cm.width_cm == 274.3
    assert state.brief_cm.depth_cm == 335.3


def test_typed_brief_text_creates_valid_room_brief() -> None:
    parsed = parse_room_brief_text("9 by 11 ft living room, Rs 60000, warm wood, kids play here")
    brief = create_room_brief(**parsed)
    assert brief.room_type == "living_room"
    assert brief.width == 9
    assert brief.depth == 11
    assert brief.units == "ft"
    assert brief.budget_inr == 60000
    assert "warm" in brief.style_words
    assert "wood" in brief.style_words
    assert "kid-friendly" in brief.constraints


def test_graph_state_shape_contains_room_brief() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    state = create_initial_state("graph-session", brief)
    graph_state = to_graph_state(state)
    assert graph_state["session_id"] == "graph-session"
    assert graph_state["brief"]["room_type"] == "living_room"
    assert graph_state["brief_cm"] == {"width_cm": 274.3, "depth_cm": 335.3}


def test_room_brief_persists_after_three_messages() -> None:
    parsed = parse_room_brief_text("9 by 11 ft living room, Rs 60000, warm wood, kids play here")
    brief = create_room_brief(**parsed)
    store = InMemoryStateStore()
    store.create("persist-session", brief)
    store.append_message("persist-session", "user", "show options")
    store.append_message("persist-session", "assistant", "I will plan around the brief.")
    state = store.append_message("persist-session", "user", "keep it kid friendly")
    assert len(state.messages) == 3
    assert state.brief == brief
    assert state.brief_cm is not None
    assert state.brief_cm.width_cm == 274.3
