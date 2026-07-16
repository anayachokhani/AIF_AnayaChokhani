from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from formaos.agents.grounder import DEFAULT_CATALOGUE_PATH, GrounderOutput
from formaos.contracts import CatalogueItem, CheckStatus, RoomBrief
from formaos.vastu.checker import VastuCheckResult, check_vastu


CheckName = Literal["fit", "budget", "sourceability", "vastu"]


class CriticValidationError(ValueError):
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.code = "critic_validation_failed"
        self.original_error = original_error


class CriticCheckResult(BaseModel):
    name: CheckName
    status: CheckStatus
    notes: list[str] = Field(default_factory=list)


class CriticVerdict(BaseModel):
    passed: bool
    fit: CriticCheckResult
    budget: CriticCheckResult
    sourceability: CriticCheckResult
    vastu: CriticCheckResult
    total_price_inr: int
    repair_notes: list[str] = Field(default_factory=list)
    vastu_result: VastuCheckResult | None = None


def load_catalogue_ids(catalogue_path: Path = DEFAULT_CATALOGUE_PATH) -> set[str]:
    with catalogue_path.open(newline="", encoding="utf-8") as handle:
        return {row["item_id"] for row in csv.DictReader(handle)}


def selected_items(grounded: GrounderOutput) -> list[CatalogueItem]:
    return [slot.selected_item for slot in grounded.grounded_slots if slot.selected_item is not None]


def check_fit(grounded: GrounderOutput) -> CriticCheckResult:
    notes: list[str] = []
    checked_count = 0
    pending_categories: list[str] = []
    for grounded_slot in grounded.grounded_slots:
        item = grounded_slot.selected_item
        if item is None:
            pending_categories.append(grounded_slot.slot.category.replace("_", " "))
            continue
        checked_count += 1
        constraints = grounded_slot.constraints
        if item.width_cm > constraints.max_width_cm:
            notes.append(
                f"Replace {item.item_id}: width {item.width_cm:.1f} cm exceeds "
                f"{constraints.max_width_cm:.1f} cm for {grounded_slot.slot.slot_id}."
            )
        if item.depth_cm > constraints.max_depth_cm:
            notes.append(
                f"Replace {item.item_id}: depth {item.depth_cm:.1f} cm exceeds "
                f"{constraints.max_depth_cm:.1f} cm for {grounded_slot.slot.slot_id}."
            )
    if notes:
        return CriticCheckResult(name="fit", status=CheckStatus.FAIL, notes=notes)
    summary = f"All {checked_count} selected items fit within their approved room footprints."
    if pending_categories:
        summary += f" Fit will be checked for {', '.join(pending_categories)} after a catalogue item is selected."
    return CriticCheckResult(name="fit", status=CheckStatus.PASS, notes=[summary])


def check_budget(brief: RoomBrief, items: list[CatalogueItem]) -> tuple[CriticCheckResult, int]:
    total = sum(item.price_inr for item in items)
    notes: list[str] = []
    if total > brief.budget_inr:
        notes.append(
            f"Reduce total price by at least INR {total - brief.budget_inr}; "
            f"selected items total INR {total} exceeds budget INR {brief.budget_inr}."
        )
    return CriticCheckResult(name="budget", status=CheckStatus.FAIL if notes else CheckStatus.PASS, notes=notes), total


def check_sourceability(grounded: GrounderOutput, catalogue_ids: set[str]) -> CriticCheckResult:
    notes: list[str] = []
    for grounded_slot in grounded.grounded_slots:
        item = grounded_slot.selected_item
        if item is None:
            failure = grounded_slot.failure
            reason = failure.blocked_by if failure else "missing catalogue selection"
            notes.append(
                f"Select an available {grounded_slot.slot.category.replace('_', ' ')}; catalogue matching was blocked by {reason}."
            )
        elif item.item_id not in catalogue_ids:
            notes.append(f"Replace fake or unavailable item ID {item.item_id} with a curated catalogue item.")
    return CriticCheckResult(name="sourceability", status=CheckStatus.FAIL if notes else CheckStatus.PASS, notes=notes)


def check_vastu_if_requested(brief: RoomBrief, items: list[CatalogueItem]) -> tuple[CriticCheckResult, VastuCheckResult | None]:
    if not brief.vastu_enabled:
        return CriticCheckResult(name="vastu", status=CheckStatus.SKIPPED, notes=["Vastu guidance was not requested."]), None
    result = check_vastu(brief, items)
    notes = result.notes
    status = CheckStatus.FAIL if any(item.badge == "fail" for item in result.item_results) else CheckStatus.WARN if notes else CheckStatus.PASS
    return CriticCheckResult(name="vastu", status=status, notes=notes), result


def critique_design(
    brief: RoomBrief | dict[str, Any],
    grounded: GrounderOutput | dict[str, Any],
    *,
    catalogue_path: Path = DEFAULT_CATALOGUE_PATH,
) -> CriticVerdict:
    try:
        valid_brief = brief if isinstance(brief, RoomBrief) else RoomBrief.model_validate(brief)
        valid_grounded = grounded if isinstance(grounded, GrounderOutput) else GrounderOutput.model_validate(grounded)
    except (ValidationError, ValueError) as exc:
        raise CriticValidationError("Critic received invalid RoomBrief or GrounderOutput.", original_error=exc) from exc

    try:
        catalogue_ids = load_catalogue_ids(catalogue_path)
    except OSError as exc:
        raise CriticValidationError("Critic could not load curated catalogue IDs.", original_error=exc) from exc

    items = selected_items(valid_grounded)
    fit = check_fit(valid_grounded)
    budget, total_price = check_budget(valid_brief, items)
    sourceability = check_sourceability(valid_grounded, catalogue_ids)
    vastu, vastu_result = check_vastu_if_requested(valid_brief, items)
    checks = [fit, budget, sourceability, vastu]
    passed = all(check.status in {CheckStatus.PASS, CheckStatus.WARN, CheckStatus.SKIPPED} for check in checks)
    repair_notes = [note for check in checks for note in check.notes if check.status in {CheckStatus.FAIL, CheckStatus.WARN}]
    return CriticVerdict(
        passed=passed,
        fit=fit,
        budget=budget,
        sourceability=sourceability,
        vastu=vastu,
        total_price_inr=total_price,
        repair_notes=repair_notes,
        vastu_result=vastu_result,
    )
