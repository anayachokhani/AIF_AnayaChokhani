from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from formaos.catalogue.index_catalogue import search_items
from formaos.contracts import CatalogueItem, DesignSlot, Direction, RoomBrief
from formaos.placement.zones import PlacementZoneError, assign_zone_for_slot
from formaos.room_state import brief_dimensions_cm


DEFAULT_CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")
DEFAULT_CHROMA_PATH = Path("data/vectorstores/chroma")
MIN_ALTERNATIVES = 2
MAX_ALTERNATIVES = 3
FailureCode = Literal["category", "width", "depth", "dimensions", "budget", "retrieval"]

ROOM_CATEGORY_TITLE_RULES: dict[tuple[str, str], tuple[set[str], set[str]]] = {
    ("bedroom", "storage"): (
        {"wardrobe", "dresser", "drawer", "organizer", "shelf", "cabinet"},
        {"coffee table", "ottoman", "bench", "desk", "container", "folder", "recliner"},
    ),
    ("bedroom", "cabinet"): (
        {"wardrobe", "dresser", "drawer", "sideboard", "bookcase", "cabinet"},
        {"media", "tv", "filing", "shoe"},
    ),
    ("bedroom", "table"): (
        {"side table", "bedside", "nightstand"},
        {"coffee table", "dining"},
    ),
    ("living_room", "storage"): (
        {"media", "console", "cabinet", "sideboard", "shelf"},
        {"folder", "container", "desk", "recliner"},
    ),
    ("study", "storage"): (
        {"file", "drawer", "organizer", "shelf", "bookcase", "cabinet"},
        {"coffee table", "ottoman", "bench", "container"},
    ),
    ("study", "cabinet"): (
        {"file", "bookcase", "drawer", "cabinet", "shelf"},
        {"media", "tv", "shoe"},
    ),
}


class GrounderValidationError(ValueError):
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.code = "grounder_validation_failed"
        self.original_error = original_error


class SlotConstraints(BaseModel):
    max_width_cm: float = Field(..., gt=0)
    max_depth_cm: float = Field(..., gt=0)
    max_price_inr: int = Field(..., gt=0)


class GroundingFailure(BaseModel):
    slot_id: str
    category: str
    code: FailureCode
    blocked_by: str
    message: str
    constraints: SlotConstraints
    query: str


class GroundedSlot(BaseModel):
    slot: DesignSlot
    placement_zone: Direction
    constraints: SlotConstraints
    selected_item: CatalogueItem | None = None
    alternatives: list[CatalogueItem] = Field(default_factory=list, max_length=MAX_ALTERNATIVES)
    failure: GroundingFailure | None = None

    @model_validator(mode="after")
    def contains_item_or_failure(self) -> "GroundedSlot":
        if self.selected_item is not None and self.selected_item.placement_zone != self.placement_zone:
            raise ValueError("selected item placement zone must match grounded slot zone")
        invalid_alternatives = [
            item.item_id for item in self.alternatives if item.placement_zone != self.placement_zone
        ]
        if invalid_alternatives:
            raise ValueError(f"alternative placement zones must match grounded slot zone: {invalid_alternatives}")
        if self.selected_item is None and self.failure is None:
            raise ValueError("grounded slot must contain either a selected item or a failure")
        if self.selected_item is not None and self.failure is not None:
            raise ValueError("grounded slot cannot contain both a selected item and a failure")
        return self


class GrounderOutput(BaseModel):
    grounded_slots: list[GroundedSlot] = Field(..., min_length=1)

    @property
    def selected_items(self) -> list[CatalogueItem]:
        return [slot.selected_item for slot in self.grounded_slots if slot.selected_item is not None]

    @property
    def failures(self) -> list[GroundingFailure]:
        return [slot.failure for slot in self.grounded_slots if slot.failure is not None]


def compute_slot_budget_inr(brief: RoomBrief, slot: DesignSlot) -> int:
    return max(1, round(brief.budget_inr * slot.budget_share))


def compute_slot_limits(brief: RoomBrief, slot: DesignSlot) -> SlotConstraints:
    dims = brief_dimensions_cm(brief)
    constraint_text = " ".join(brief.constraints).lower()
    constraint_multiplier = 1.0
    if any(term in constraint_text for term in ["play", "kid", "child", "circulation", "walkway", "wheelchair"]):
        constraint_multiplier = 0.9
    if slot.category in {"sofa", "loveseat", "bed"}:
        constraint_multiplier = max(constraint_multiplier, 0.95)
    placement_limits: dict[Direction | None, tuple[float, float]] = {
        "C": (dims.width_cm * 0.8, dims.depth_cm * 0.65),
        "N": (dims.width_cm * 0.85, dims.depth_cm * 0.4),
        "S": (dims.width_cm * 0.85, dims.depth_cm * 0.4),
        "E": (dims.width_cm * 0.45, dims.depth_cm * 0.85),
        "W": (dims.width_cm * 0.45, dims.depth_cm * 0.85),
        "NE": (dims.width_cm * 0.55, dims.depth_cm * 0.55),
        "NW": (dims.width_cm * 0.55, dims.depth_cm * 0.55),
        "SE": (dims.width_cm * 0.55, dims.depth_cm * 0.55),
        "SW": (dims.width_cm * 0.55, dims.depth_cm * 0.55),
        None: (dims.width_cm * 0.75, dims.depth_cm * 0.6),
    }
    placement_width, placement_depth = placement_limits[slot.placement_hint]
    if slot.category == "bed" and slot.placement_hint in {"NE", "NW", "SE", "SW"}:
        placement_width = dims.width_cm * 0.75
        placement_depth = dims.depth_cm * 0.75
    target_width = slot.target_width_cm if slot.target_width_cm is not None else placement_width
    target_depth = slot.target_depth_cm if slot.target_depth_cm is not None else placement_depth
    return SlotConstraints(
        max_width_cm=round(min(target_width, placement_width) * constraint_multiplier, 1),
        max_depth_cm=round(min(target_depth, placement_depth) * constraint_multiplier, 1),
        max_price_inr=compute_slot_budget_inr(brief, slot),
    )


def slot_query(slot: DesignSlot) -> str:
    parts = [slot.style_text, slot.category, *slot.must_have_constraints]
    return " ".join(part for part in parts if part).strip() or slot.category


def room_relevance_score(brief: RoomBrief, slot: DesignSlot, item: dict[str, Any]) -> tuple[float, float]:
    preferred, discouraged = ROOM_CATEGORY_TITLE_RULES.get((brief.room_type, slot.category), (set(), set()))
    title = str(item.get("title") or "").lower()
    semantic_penalty = 0.0
    if preferred and not any(term in title for term in preferred):
        semantic_penalty += 2.0
    semantic_penalty -= sum(1.0 for term in preferred if term in title)
    semantic_penalty += sum(8.0 for term in discouraged if term in title)
    return semantic_penalty, float(item.get("distance") or 0.0)


def catalogue_item_from_metadata(metadata: dict[str, Any], placement_zone: Direction | None = None) -> CatalogueItem:
    return CatalogueItem(
        item_id=str(metadata["item_id"]),
        title=str(metadata["title"]),
        product_type=str(metadata["category"]),
        width_cm=float(metadata["width_cm"]),
        depth_cm=float(metadata["depth_cm"]),
        height_cm=float(metadata["height_cm"]) if metadata.get("height_cm") not in {None, ""} else None,
        material=str(metadata.get("material") or "") or None,
        color=str(metadata.get("color") or "") or None,
        style_text="",
        price_inr=int(metadata["price_inr"]),
        image_path=str(metadata.get("image_path") or "") or None,
        image_available=bool(metadata.get("image_available")),
        source_dataset="ABO",
        placement_zone=placement_zone,
    )


def load_catalogue_rows(catalogue_path: Path) -> list[dict[str, str]]:
    with catalogue_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def diagnose_failure(
    slot: DesignSlot,
    constraints: SlotConstraints,
    query: str,
    *,
    catalogue_path: Path,
) -> GroundingFailure:
    rows = load_catalogue_rows(catalogue_path)
    category_rows = [row for row in rows if row.get("normalized_category") == slot.category]
    if not category_rows:
        code: FailureCode = "category"
        blocked_by = "category_unavailable"
    else:
        width_rows = [row for row in category_rows if float(row["width_cm"]) <= constraints.max_width_cm]
        depth_rows = [row for row in category_rows if float(row["depth_cm"]) <= constraints.max_depth_cm]
        dimension_rows = [
            row
            for row in category_rows
            if float(row["width_cm"]) <= constraints.max_width_cm and float(row["depth_cm"]) <= constraints.max_depth_cm
        ]
        if not dimension_rows:
            if not width_rows:
                code = "width"
                blocked_by = "maximum_width_exceeded"
            elif not depth_rows:
                code = "depth"
                blocked_by = "maximum_depth_exceeded"
            else:
                code = "dimensions"
                blocked_by = "dimension_combination_exceeded"
        elif not any(int(row["price_inr"]) <= constraints.max_price_inr for row in dimension_rows):
            code = "budget"
            blocked_by = "budget_exceeded"
        else:
            code = "retrieval"
            blocked_by = "no_catalogue_match"

    return GroundingFailure(
        slot_id=slot.slot_id,
        category=slot.category,
        code=code,
        blocked_by=blocked_by,
        message=(
            f"No catalogue item fit slot {slot.slot_id}; blocked by {blocked_by} "
            f"with max {constraints.max_width_cm} x {constraints.max_depth_cm} cm "
            f"and INR {constraints.max_price_inr} budget."
        ),
        constraints=constraints,
        query=query,
    )


def ground_slot(
    brief: RoomBrief,
    slot: DesignSlot,
    *,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
) -> GroundedSlot:
    try:
        placement_zone = assign_zone_for_slot(slot)
    except PlacementZoneError as exc:
        raise GrounderValidationError("Grounder received invalid placement hint.", original_error=exc) from exc
    try:
        constraints = compute_slot_limits(brief, slot)
    except KeyError as exc:
        raise GrounderValidationError("Grounder received invalid placement hint.", original_error=exc) from exc
    query = slot_query(slot)
    results = search_items(
        query,
        category=slot.category,
        max_width_cm=constraints.max_width_cm,
        max_depth_cm=constraints.max_depth_cm,
        max_price_inr=constraints.max_price_inr,
        k=15,
        chroma_path=chroma_path,
    )
    results = sorted(results, key=lambda item: room_relevance_score(brief, slot, item))
    if len(results) < MIN_ALTERNATIVES + 1:
        return GroundedSlot(
            slot=slot,
            placement_zone=placement_zone,
            constraints=constraints,
            failure=diagnose_failure(slot, constraints, query, catalogue_path=catalogue_path),
        )

    selected = catalogue_item_from_metadata(results[0], placement_zone)
    alternatives = [catalogue_item_from_metadata(result, placement_zone) for result in results[1 : MAX_ALTERNATIVES + 1]]
    try:
        return GroundedSlot(
            slot=slot,
            placement_zone=placement_zone,
            constraints=constraints,
            selected_item=selected,
            alternatives=alternatives,
        )
    except (ValidationError, ValueError) as exc:
        raise GrounderValidationError("Grounder produced invalid slot output.", original_error=exc) from exc


def ground_design(
    brief: RoomBrief | dict[str, Any],
    slots: list[DesignSlot] | list[dict[str, Any]],
    *,
    chroma_path: Path = DEFAULT_CHROMA_PATH,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
) -> GrounderOutput:
    try:
        valid_brief = brief if isinstance(brief, RoomBrief) else RoomBrief.model_validate(brief)
        valid_slots = [slot if isinstance(slot, DesignSlot) else DesignSlot.model_validate(slot) for slot in slots]
    except (ValidationError, ValueError) as exc:
        raise GrounderValidationError("Grounder received invalid RoomBrief or DesignSlot input.", original_error=exc) from exc

    if not valid_slots:
        raise GrounderValidationError("Grounder requires at least one DesignSlot.")

    grounded_slots = [
        ground_slot(valid_brief, slot, chroma_path=chroma_path, catalogue_path=catalogue_path) for slot in valid_slots
    ]
    try:
        return GrounderOutput(grounded_slots=grounded_slots)
    except (ValidationError, ValueError) as exc:
        raise GrounderValidationError("Grounder produced invalid output.", original_error=exc) from exc
