from __future__ import annotations

import re
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field

from formaos.contracts import Direction, GroundedDesign, ResponseState, RoomBrief, Units


DEFAULT_ROOM_TYPES = {
    "living_room": {
        "width": 10.0,
        "depth": 12.0,
        "units": Units.FT,
        "budget_inr": 85000,
        "style_words": ["warm", "modern"],
    },
    "bedroom": {
        "width": 10.0,
        "depth": 11.0,
        "units": Units.FT,
        "budget_inr": 90000,
        "style_words": ["calm", "storage"],
    },
    "study": {
        "width": 8.0,
        "depth": 10.0,
        "units": Units.FT,
        "budget_inr": 60000,
        "style_words": ["focused", "minimal"],
    },
}


class RoomDimensionsCm(BaseModel):
    width_cm: float = Field(..., gt=0)
    depth_cm: float = Field(..., gt=0)


class FormaOSState(BaseModel):
    session_id: str
    response_state: ResponseState = "waiting"
    brief: RoomBrief | None = None
    brief_cm: RoomDimensionsCm | None = None
    current_design: GroundedDesign | None = None
    messages: list[dict[str, str]] = Field(default_factory=list)
    attempt_log: list[dict[str, Any]] = Field(default_factory=list)


class FormaOSGraphState(TypedDict):
    session_id: str
    response_state: ResponseState
    brief: NotRequired[dict[str, Any] | None]
    brief_cm: NotRequired[dict[str, float] | None]
    current_design: NotRequired[dict[str, Any] | None]
    messages: list[dict[str, str]]
    attempt_log: list[dict[str, Any]]


def normalize_room_type(room_type: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (room_type or "living_room").strip().lower())
    normalized = normalized.strip("_")
    if normalized in {"living", "livingroom", "hall"}:
        return "living_room"
    if normalized in {"bed", "master_bedroom"}:
        return "bedroom"
    return normalized or "living_room"


def dimension_to_cm(value: float, units: Units) -> float:
    if units == Units.CM:
        return round(value, 1)
    if units == Units.M:
        return round(value * 100, 1)
    if units == Units.FT:
        return round(value * 30.48, 1)
    raise ValueError(f"Unsupported unit: {units}")


def brief_dimensions_cm(brief: RoomBrief) -> RoomDimensionsCm:
    return RoomDimensionsCm(
        width_cm=dimension_to_cm(brief.width, brief.units),
        depth_cm=dimension_to_cm(brief.depth, brief.units),
    )


def split_words(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return [word for word in re.split(r"[, ]+", value.lower()) if word]


def parse_room_brief_text(text: str) -> dict[str, Any]:
    normalized = text.lower()
    room_type = "living_room"
    if "bedroom" in normalized:
        room_type = "bedroom"
    elif "study" in normalized or "office" in normalized:
        room_type = "study"

    units = "ft" if re.search(r"\b(ft|feet|foot)\b", normalized) else None
    dimension_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(ft|feet|foot|cm|m)?",
        normalized,
    )
    width = float(dimension_match.group(1)) if dimension_match else None
    depth = float(dimension_match.group(2)) if dimension_match else None
    if dimension_match and dimension_match.group(3):
        raw_units = dimension_match.group(3)
        units = "ft" if raw_units in {"feet", "foot"} else raw_units

    budget_match = re.search(r"(?:rs|inr|₹)\s*([0-9][0-9,]*)", normalized)
    budget_inr = int(budget_match.group(1).replace(",", "")) if budget_match else None

    style_text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:by|x|×)\s*(\d+(?:\.\d+)?)\s*(ft|feet|foot|cm|m)?", " ", normalized)
    style_text = re.sub(r"(?:rs|inr|₹)\s*[0-9][0-9,]*", " ", style_text)
    style_text = re.sub(r"\b(living room|bedroom|study|office|room|ft|feet|foot|cm|m)\b", " ", style_text)
    style_words = split_words(style_text)

    constraints = []
    if "kid" in normalized or "kids" in normalized or "child" in normalized:
        constraints.append("kid-friendly")
    if "play" in normalized:
        constraints.append("play space")

    return {
        "room_type": room_type,
        "width": width,
        "depth": depth,
        "units": units,
        "budget_inr": budget_inr,
        "style_words": style_words,
        "constraints": constraints,
    }


def create_room_brief(
    *,
    room_type: str | None = None,
    width: float | None = None,
    depth: float | None = None,
    units: str | Units | None = None,
    budget_inr: int | None = None,
    style_words: str | list[str] | None = None,
    constraints: str | list[str] | None = None,
    vastu_enabled: bool = False,
    main_door_direction: Direction | None = None,
    compass_direction: Direction | None = None,
) -> RoomBrief:
    normalized_room_type = normalize_room_type(room_type)
    defaults = DEFAULT_ROOM_TYPES.get(normalized_room_type, DEFAULT_ROOM_TYPES["living_room"])
    resolved_units = Units(units or defaults["units"])
    brief = RoomBrief(
        room_type=normalized_room_type,
        width=width if width is not None else float(defaults["width"]),
        depth=depth if depth is not None else float(defaults["depth"]),
        units=resolved_units,
        budget_inr=budget_inr if budget_inr is not None else int(defaults["budget_inr"]),
        style_words=split_words(style_words) or list(defaults["style_words"]),
        constraints=split_words(constraints),
        vastu_enabled=vastu_enabled,
        main_door_direction=main_door_direction,
        compass_direction=compass_direction,
    )
    return brief


def create_initial_state(session_id: str, brief: RoomBrief) -> FormaOSState:
    return FormaOSState(
        session_id=session_id,
        response_state="waiting",
        brief=brief,
        brief_cm=brief_dimensions_cm(brief),
        messages=[],
        attempt_log=[],
    )


def to_graph_state(state: FormaOSState) -> FormaOSGraphState:
    return {
        "session_id": state.session_id,
        "response_state": state.response_state,
        "brief": state.brief.model_dump(mode="json") if state.brief else None,
        "brief_cm": state.brief_cm.model_dump() if state.brief_cm else None,
        "current_design": state.current_design.model_dump(mode="json") if state.current_design else None,
        "messages": state.messages,
        "attempt_log": state.attempt_log,
    }


def append_message(state: FormaOSState, role: str, content: str) -> FormaOSState:
    next_messages = [*state.messages, {"role": role, "content": content}]
    return state.model_copy(update={"messages": next_messages})


class InMemoryStateStore:
    def __init__(self) -> None:
        self._states: dict[str, FormaOSState] = {}

    def create(self, session_id: str, brief: RoomBrief) -> FormaOSState:
        state = create_initial_state(session_id, brief)
        self._states[session_id] = state
        return state

    def get(self, session_id: str) -> FormaOSState | None:
        return self._states.get(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> FormaOSState:
        state = self._states[session_id]
        updated = append_message(state, role, content)
        self._states[session_id] = updated
        return updated

    def clear(self) -> None:
        self._states.clear()

    def delete(self, session_id: str) -> None:
        self._states.pop(session_id, None)
