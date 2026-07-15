from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from formaos.agents.planner import ALLOWED_NEED_CATEGORIES, PlannerNeed, PlannerOutput
from formaos.contracts import DesignSlot, Direction, RoomBrief
from formaos.room_state import brief_dimensions_cm
from formaos.vastu.schema import load_rule_set


DEFAULT_CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")
MIN_SLOT_COUNT = 4
MAX_SLOT_COUNT = 10

ROOM_DEFAULT_NEEDS: dict[str, list[dict[str, object]]] = {
    "living_room": [
        {"category": "sofa", "purpose": "primary seating matched to the selected style", "priority": 1, "budget_share": 0.5},
        {"category": "chair", "purpose": "accent seating or reading chair", "priority": 2, "budget_share": 0.11},
        {"category": "table", "purpose": "coffee or side surface", "priority": 2, "budget_share": 0.12},
        {"category": "rug", "purpose": "soft zone and visual anchor", "priority": 3, "budget_share": 0.1},
        {"category": "storage", "purpose": "closed storage or media console", "priority": 3, "budget_share": 0.13},
        {"category": "cabinet", "purpose": "display cabinet or concealed storage", "priority": 4, "budget_share": 0.1},
        {"category": "lamp", "purpose": "warm layered lighting", "priority": 4, "budget_share": 0.06},
        {"category": "mirror", "purpose": "wall reflection or art-like vertical element", "priority": 5, "budget_share": 0.04},
        {"category": "planter", "purpose": "greenery and natural styling", "priority": 5, "budget_share": 0.03},
    ],
    "bedroom": [
        {"category": "bed", "purpose": "sleeping zone matched to the selected style", "priority": 1, "budget_share": 0.38},
        {"category": "storage", "purpose": "wardrobe or drawer storage", "priority": 2, "budget_share": 0.2},
        {"category": "table", "purpose": "bedside surface", "priority": 2, "budget_share": 0.08},
        {"category": "cabinet", "purpose": "secondary storage or display", "priority": 3, "budget_share": 0.1},
        {"category": "rug", "purpose": "soft landing beside the bed", "priority": 3, "budget_share": 0.08},
        {"category": "lamp", "purpose": "bedside lighting", "priority": 4, "budget_share": 0.06},
        {"category": "chair", "purpose": "reading or dressing chair", "priority": 4, "budget_share": 0.07},
        {"category": "mirror", "purpose": "dressing mirror or wall reflection", "priority": 5, "budget_share": 0.04},
        {"category": "planter", "purpose": "low-maintenance greenery", "priority": 5, "budget_share": 0.03},
    ],
    "study": [
        {"category": "desk", "purpose": "work surface matched to the selected style", "priority": 1, "budget_share": 0.3},
        {"category": "chair", "purpose": "ergonomic seating", "priority": 2, "budget_share": 0.18},
        {"category": "storage", "purpose": "document and object storage", "priority": 2, "budget_share": 0.15},
        {"category": "cabinet", "purpose": "closed storage or display", "priority": 3, "budget_share": 0.12},
        {"category": "rug", "purpose": "acoustic softness and visual anchor", "priority": 3, "budget_share": 0.08},
        {"category": "lamp", "purpose": "task lighting", "priority": 4, "budget_share": 0.06},
        {"category": "table", "purpose": "printer, side, or reading surface", "priority": 4, "budget_share": 0.06},
        {"category": "mirror", "purpose": "wall reflection or art-like vertical element", "priority": 5, "budget_share": 0.04},
        {"category": "planter", "purpose": "desk-friendly greenery", "priority": 5, "budget_share": 0.03},
    ],
}

PLACEMENT_HINTS: dict[str, Direction] = {
    "sofa": "S",
    "loveseat": "S",
    "bed": "SW",
    "cabinet": "W",
    "storage": "W",
    "table": "C",
    "desk": "E",
    "chair": "E",
    "rug": "C",
    "lamp": "SE",
    "mirror": "N",
    "planter": "NE",
}
VASTU_RULE_PATH = Path("data/vastu/vastu_rules_v1.json")
VASTU_SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}


class DesignerOutput(BaseModel):
    slots: list[DesignSlot] = Field(..., min_length=MIN_SLOT_COUNT, max_length=MAX_SLOT_COUNT)
    concept_image_prompt: str | None = None

    @model_validator(mode="after")
    def budget_shares_sum_close_to_one(self) -> "DesignerOutput":
        total = sum(slot.budget_share for slot in self.slots)
        if not 0.98 <= total <= 1.02:
            raise ValueError(f"slot budget shares must sum close to 1.0, got {total:.3f}")
        return self


class DesignerValidationError(ValueError):
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.code = "designer_validation_failed"
        self.original_error = original_error


def load_catalogue_categories(catalogue_path: Path = DEFAULT_CATALOGUE_PATH) -> set[str]:
    if not catalogue_path.exists():
        return set(ALLOWED_NEED_CATEGORIES)
    with catalogue_path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {row["normalized_category"] for row in rows if row.get("normalized_category")}


def planner_need_from_default(default: dict[str, object], brief: RoomBrief) -> PlannerNeed:
    return PlannerNeed(
        category=str(default["category"]),
        purpose=str(default["purpose"]),
        quantity=1,
        priority=int(default["priority"]),
        budget_share=float(default["budget_share"]),
        style_tags=brief.style_words,
        constraints=brief.constraints,
    )


def validate_designer_inputs(brief: RoomBrief | dict[str, Any], planner_output: PlannerOutput | dict[str, Any]) -> tuple[RoomBrief, PlannerOutput]:
    try:
        valid_brief = brief if isinstance(brief, RoomBrief) else RoomBrief.model_validate(brief)
        valid_planner_output = (
            planner_output
            if isinstance(planner_output, PlannerOutput)
            else PlannerOutput.model_validate(planner_output)
        )
    except (ValidationError, ValueError) as exc:
        raise DesignerValidationError("Designer received invalid RoomBrief or PlannerOutput.", original_error=exc) from exc

    dims = brief_dimensions_cm(valid_brief)
    facts = valid_planner_output.room_facts
    mismatches: list[str] = []
    if facts.room_type != valid_brief.room_type:
        mismatches.append("room_type")
    if facts.width_cm != dims.width_cm or facts.depth_cm != dims.depth_cm:
        mismatches.append("room_dimensions")
    if facts.budget_inr != valid_brief.budget_inr:
        mismatches.append("budget")
    if facts.style_words != valid_brief.style_words:
        mismatches.append("style_words")
    if mismatches:
        raise DesignerValidationError(f"PlannerOutput does not preserve RoomBrief fields: {', '.join(mismatches)}")
    return valid_brief, valid_planner_output


def complete_needs(brief: RoomBrief, planner_output: PlannerOutput) -> list[PlannerNeed]:
    selected: list[PlannerNeed] = sorted(planner_output.needs_list, key=lambda need: need.priority)
    existing_categories = {need.category for need in selected}
    defaults = ROOM_DEFAULT_NEEDS.get(brief.room_type, ROOM_DEFAULT_NEEDS["living_room"])
    default_by_category = {str(default["category"]): default for default in defaults}
    for need in selected:
        default = default_by_category.get(need.category)
        if default:
            need.budget_share = max(need.budget_share, float(default["budget_share"]))
    target_count = len(defaults)
    if brief.budget_inr < 100_000:
        target_count = MIN_SLOT_COUNT
    elif brief.budget_inr < 180_000:
        target_count = min(7, len(defaults))
    for default in defaults:
        if len(selected) >= min(MAX_SLOT_COUNT, target_count):
            break
        category = str(default["category"])
        if category not in existing_categories:
            selected.append(planner_need_from_default(default, brief))
            existing_categories.add(category)
    return sorted(selected, key=lambda need: need.priority)[:MAX_SLOT_COUNT]


def normalize_budget_shares(needs: list[PlannerNeed]) -> list[float]:
    raw_total = sum(max(need.budget_share, 0.01) for need in needs)
    normalized = [round(max(need.budget_share, 0.01) / raw_total, 4) for need in needs]
    drift = round(1.0 - sum(normalized), 4)
    normalized[-1] = round(normalized[-1] + drift, 4)
    return normalized


def footprint_for_need(brief: RoomBrief, need: PlannerNeed) -> tuple[float, float]:
    dims = brief_dimensions_cm(brief)
    category_defaults = {
        "sofa": (min(dims.width_cm * 0.68, 230), min(dims.depth_cm * 0.36, 105)),
        "loveseat": (min(dims.width_cm * 0.55, 190), min(dims.depth_cm * 0.34, 100)),
        "bed": (min(dims.width_cm * 0.85, 220), min(dims.depth_cm * 0.82, 220)),
        "cabinet": (min(dims.width_cm * 0.45, 140), min(dims.depth_cm * 0.22, 60)),
        "storage": (min(dims.width_cm * 0.5, 160), min(dims.depth_cm * 0.24, 65)),
        "table": (min(dims.width_cm * 0.42, 130), min(dims.depth_cm * 0.28, 90)),
        "desk": (min(dims.width_cm * 0.65, 160), min(dims.depth_cm * 0.3, 80)),
        "chair": (min(dims.width_cm * 0.32, 90), min(dims.depth_cm * 0.32, 95)),
        "rug": (min(dims.width_cm * 0.78, 300), min(dims.depth_cm * 0.62, 300)),
        "lamp": (45.0, 45.0),
        "mirror": (min(dims.width_cm * 0.28, 90), 10.0),
        "planter": (45.0, 45.0),
    }
    default_width, default_depth = category_defaults[need.category]
    return (
        round(min(need.max_width_cm or default_width, default_width), 1),
        round(min(need.max_depth_cm or default_depth, default_depth), 1),
    )


def style_text_for(brief: RoomBrief, need: PlannerNeed) -> str:
    terms = [*brief.style_words, *need.style_tags, need.purpose, need.category]
    deduped: list[str] = []
    for term in terms:
        normalized = term.strip().lower()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return " ".join(deduped)


def placement_hint_for(brief: RoomBrief, category: str) -> Direction | None:
    fallback = PLACEMENT_HINTS.get(category)
    if not brief.vastu_enabled:
        return fallback
    try:
        rules = load_rule_set(VASTU_RULE_PATH).rules
    except (OSError, ValueError):
        return fallback
    applicable = [
        rule
        for rule in rules
        if rule.room_type in {"any", brief.room_type}
        and rule.object_class == category
        and rule.perspective in {"placement", "clearance"}
    ]
    applicable.sort(
        key=lambda rule: (
            0 if rule.room_type == brief.room_type else 1,
            VASTU_SEVERITY_ORDER[rule.severity],
            -rule.confidence,
        )
    )
    avoided = {zone for rule in applicable for zone in rule.avoided_zones}
    for rule in applicable:
        preferred = next((zone for zone in rule.preferred_zones if zone not in avoided), None)
        if preferred:
            return preferred
    return fallback if fallback not in avoided else None


def validate_categories(slots: list[DesignSlot], catalogue_categories: set[str]) -> None:
    invalid = sorted({slot.category for slot in slots if slot.category not in catalogue_categories})
    if invalid:
        raise DesignerValidationError(f"slot categories not present in curated catalogue: {', '.join(invalid)}")


def build_concept_prompt(brief: RoomBrief, slots: list[DesignSlot]) -> str:
    slot_text = ", ".join(f"{slot.quantity} {slot.category}" for slot in slots)
    style = ", ".join(brief.style_words) if brief.style_words else "practical"
    return (
        f"Interior concept for a {brief.room_type.replace('_', ' ')} with {style} styling; "
        f"include {slot_text}; respect constraints: {', '.join(brief.constraints) or 'none'}."
    )


def design_slots(
    brief: RoomBrief | dict[str, Any],
    planner_output: PlannerOutput | dict[str, Any],
    *,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
    include_concept_prompt: bool = False,
) -> DesignerOutput:
    brief, planner_output = validate_designer_inputs(brief, planner_output)
    needs = complete_needs(brief, planner_output)
    shares = normalize_budget_shares(needs)
    slots: list[DesignSlot] = []
    for index, (need, share) in enumerate(zip(needs, shares), start=1):
        width_cm, depth_cm = footprint_for_need(brief, need)
        constraints = [*planner_output.constraints, *need.constraints]
        slots.append(
            DesignSlot(
                slot_id=f"slot_{index}_{need.category}",
                category=need.category,
                quantity=need.quantity,
                target_width_cm=width_cm,
                target_depth_cm=depth_cm,
                style_text=style_text_for(brief, need),
                budget_share=share,
                must_have_constraints=list(dict.fromkeys(constraints)),
                placement_hint=placement_hint_for(brief, need.category),
            )
        )

    catalogue_categories = load_catalogue_categories(catalogue_path)
    validate_categories(slots, catalogue_categories)
    concept_prompt = build_concept_prompt(brief, slots) if include_concept_prompt else None
    try:
        return DesignerOutput(slots=slots, concept_image_prompt=concept_prompt)
    except (ValidationError, ValueError) as exc:
        raise DesignerValidationError("Designer produced invalid DesignSlot output.", original_error=exc) from exc
