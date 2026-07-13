from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from formaos.agents.critic import CriticVerdict
from formaos.contracts import DesignSlot, Direction
from formaos.placement.zones import ZONES


ZONE_PATTERN = re.compile(r"\bin\s+((?:NW|NE|SW|SE|N|S|E|W|C)(?:,\s*(?:NW|NE|SW|SE|N|S|E|W|C))*)\b")
WIDTH_PATTERN = re.compile(r"width\s+[0-9.]+\s+cm\s+exceeds\s+([0-9.]+)\s+cm\s+for\s+([a-zA-Z0-9_]+)")
DEPTH_PATTERN = re.compile(r"depth\s+[0-9.]+\s+cm\s+exceeds\s+([0-9.]+)\s+cm\s+for\s+([a-zA-Z0-9_]+)")
CATEGORY_TERMS = {
    "bed": {"bed"},
    "storage": {"storage", "wardrobe", "cabinet"},
    "cabinet": {"cabinet"},
    "sofa": {"sofa", "loveseat", "seating"},
    "loveseat": {"loveseat"},
    "table": {"table"},
    "rug": {"rug"},
    "lamp": {"lamp", "lighting"},
    "desk": {"desk"},
    "chair": {"chair"},
    "mirror": {"mirror"},
    "planter": {"planter"},
}


class ReviserValidationError(ValueError):
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.code = "reviser_validation_failed"
        self.original_error = original_error


class ReviserOutput(BaseModel):
    slots: list[DesignSlot] = Field(..., min_length=1)
    notes: list[str] = Field(default_factory=list)
    changed_slots: list[str] = Field(default_factory=list)
    changed_items: list[str] = Field(default_factory=list)


def first_zone_from_note(note: str) -> Direction | None:
    matches = ZONE_PATTERN.findall(note)
    if not matches:
        return None
    first = matches[-1].split(",")[0].strip()
    return first if first in ZONES else None


def category_matches_note(category: str, note: str) -> bool:
    lowered = note.lower()
    terms = CATEGORY_TERMS.get(category, {category})
    return any(term in lowered for term in terms)


def revise_slots(slots: list[DesignSlot] | list[dict[str, Any]], verdict: CriticVerdict | dict[str, Any]) -> ReviserOutput:
    try:
        valid_slots = [slot if isinstance(slot, DesignSlot) else DesignSlot.model_validate(slot) for slot in slots]
        valid_verdict = verdict if isinstance(verdict, CriticVerdict) else CriticVerdict.model_validate(verdict)
    except (ValidationError, ValueError) as exc:
        raise ReviserValidationError("Reviser received invalid slots or Critic verdict.", original_error=exc) from exc

    revised = [slot.model_copy(deep=True) for slot in valid_slots]
    notes: list[str] = []
    changed_slots: list[str] = []

    for note in valid_verdict.repair_notes:
        zone = first_zone_from_note(note)
        if zone is not None:
            for index, slot in enumerate(revised):
                if category_matches_note(slot.category, note):
                    if slot.placement_hint != zone:
                        revised[index] = slot.model_copy(update={"placement_hint": zone})
                        changed_slots.append(slot.slot_id)
                        notes.append(f"Set {slot.slot_id} placement hint to {zone} from Critic note.")

        width_match = WIDTH_PATTERN.search(note)
        if width_match:
            max_width = float(width_match.group(1))
            slot_id = width_match.group(2)
            for index, slot in enumerate(revised):
                if slot.slot_id == slot_id and (slot.target_width_cm is None or slot.target_width_cm > max_width):
                    revised[index] = slot.model_copy(update={"target_width_cm": max_width})
                    changed_slots.append(slot.slot_id)
                    notes.append(f"Reduced {slot.slot_id} target width to {max_width:.1f} cm.")

        depth_match = DEPTH_PATTERN.search(note)
        if depth_match:
            max_depth = float(depth_match.group(1))
            slot_id = depth_match.group(2)
            for index, slot in enumerate(revised):
                if slot.slot_id == slot_id and (slot.target_depth_cm is None or slot.target_depth_cm > max_depth):
                    revised[index] = slot.model_copy(update={"target_depth_cm": max_depth})
                    changed_slots.append(slot.slot_id)
                    notes.append(f"Reduced {slot.slot_id} target depth to {max_depth:.1f} cm.")

    deduped_changed_slots = list(dict.fromkeys(changed_slots))
    if not notes:
        notes.append("No deterministic slot edit matched the Critic notes.")
    return ReviserOutput(
        slots=revised,
        notes=notes,
        changed_slots=deduped_changed_slots,
        changed_items=[],
    )
