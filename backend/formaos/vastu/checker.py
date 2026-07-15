from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from formaos.contracts import CatalogueItem, Direction, RoomBrief
from formaos.placement.zones import is_valid_zone
from formaos.vastu.schema import VastuRule, load_rule_set


DEFAULT_RULE_PATH = Path("data/vastu/vastu_rules_v1.json")
RuleStatus = Literal["pass", "warn", "fail"]

SEVERITY_WEIGHTS = {
    "critical": 3,
    "warn": 2,
    "info": 1,
}

SEVERITY_LABELS = {
    "critical": "must",
    "warn": "should",
    "info": "nice",
}

GENERIC_OBJECT_CLASSES = {
    "heavy_furniture": {"bed", "sofa", "loveseat", "storage", "cabinet"},
    "central_clearance": {"rug", "table"},
}
OBJECT_CLASS_ALIASES = {
    "wardrobe": "storage",
    "lighting": "lamp",
    "coffee_table": "table",
}


class VastuCheckerError(ValueError):
    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.code = "vastu_checker_validation_failed"
        self.original_error = original_error


class VastuRuleResult(BaseModel):
    rule_id: str
    item_id: str
    object_class: str
    zone: Direction
    status: RuleStatus
    severity: str
    weight: int = Field(..., ge=1, le=3)
    badge: str
    note: str
    rationale: str


class VastuItemResult(BaseModel):
    item_id: str
    title: str
    object_class: str
    zone: Direction
    badge: RuleStatus
    notes: list[str]
    rule_results: list[VastuRuleResult]


class VastuCheckResult(BaseModel):
    score: int = Field(..., ge=0, le=100)
    total_weight: int = Field(..., ge=0)
    earned_weight: float = Field(..., ge=0)
    item_results: list[VastuItemResult]
    notes: list[str]


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def item_terms(item: CatalogueItem) -> set[str]:
    raw = " ".join(
        [
            normalize_text(item.product_type),
            normalize_text(item.color),
            normalize_text(item.material),
            normalize_text(item.style_text),
            normalize_text(item.title),
        ]
    )
    terms = {term for term in raw.replace("/", " ").replace(",", " ").split() if term}
    for value in [item.color, item.material, item.style_text]:
        normalized = normalize_text(value)
        if normalized:
            terms.add(normalized)
    return terms


def normalized_item_object_class(item: CatalogueItem) -> str:
    product_type = normalize_text(item.product_type)
    return OBJECT_CLASS_ALIASES.get(product_type, product_type)


def rule_matches_item(rule: VastuRule, brief: RoomBrief, item: CatalogueItem) -> bool:
    if rule.room_type not in {"any", brief.room_type}:
        return False
    product_type = normalized_item_object_class(item)
    if rule.object_class == product_type:
        return True
    return product_type in GENERIC_OBJECT_CLASSES.get(rule.object_class, set())


def rule_status_for_item(rule: VastuRule, item: CatalogueItem) -> RuleStatus:
    zone = item.placement_zone
    if zone is None or not is_valid_zone(zone):
        raise VastuCheckerError(f"item {item.item_id} has invalid placement zone: {zone}")

    terms = item_terms(item)
    if rule.perspective in {"placement", "clearance"}:
        if zone in rule.avoided_zones:
            return "fail" if rule.severity == "critical" else "warn"
        if rule.preferred_zones and zone not in rule.preferred_zones:
            return "fail" if rule.severity == "critical" else "warn"
    if rule.perspective == "color":
        if any(color in terms for color in rule.avoided_colors):
            return "fail" if rule.severity == "critical" else "warn"
        if rule.preferred_colors and not any(color in terms for color in rule.preferred_colors):
            return "warn"
    return "pass"


def actionable_note(rule: VastuRule, item: CatalogueItem, status: RuleStatus) -> str:
    label = SEVERITY_LABELS[rule.severity]
    if status == "pass":
        return f"{label}: {item.title} satisfies {rule.rule_id} in zone {item.placement_zone}."
    if rule.perspective in {"placement", "clearance"} and item.placement_zone in rule.avoided_zones:
        preferred = ", ".join(rule.preferred_zones) or "a preferred zone"
        return f"{label}: move {item.title} from {item.placement_zone} to {preferred}."
    if rule.perspective in {"placement", "clearance"} and rule.preferred_zones and item.placement_zone not in rule.preferred_zones:
        return f"{label}: consider placing {item.title} in {', '.join(rule.preferred_zones)}."
    if rule.perspective == "color" and rule.avoided_colors:
        return f"{label}: avoid {', '.join(rule.avoided_colors)} for {item.title}."
    if rule.perspective == "color" and rule.preferred_colors:
        return f"{label}: prefer {', '.join(rule.preferred_colors)} tones/material cues for {item.title}."
    return f"{label}: review {item.title} against {rule.rule_id}."


def badge_for_rule(status: RuleStatus) -> str:
    return {"pass": "aligned", "warn": "review", "fail": "repair"}[status]


def badge_for_item(rule_results: list[VastuRuleResult]) -> RuleStatus:
    statuses = {result.status for result in rule_results}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def score_from_results(results: list[VastuRuleResult]) -> tuple[int, int, float]:
    total = sum(result.weight for result in results)
    if total == 0:
        return 100, 0, 0.0
    earned = 0.0
    for result in results:
        if result.status == "pass":
            earned += result.weight
        elif result.status == "warn":
            earned += result.weight * 0.5
    return round((earned / total) * 100), total, earned


def check_vastu(
    brief: RoomBrief | dict,
    items: list[CatalogueItem] | list[dict],
    *,
    rule_path: Path = DEFAULT_RULE_PATH,
) -> VastuCheckResult:
    try:
        valid_brief = brief if isinstance(brief, RoomBrief) else RoomBrief.model_validate(brief)
        valid_items = [item if isinstance(item, CatalogueItem) else CatalogueItem.model_validate(item) for item in items]
        rule_set = load_rule_set(rule_path)
    except (ValidationError, ValueError) as exc:
        raise VastuCheckerError("Vastu checker received invalid input.", original_error=exc) from exc

    item_results: list[VastuItemResult] = []
    all_rule_results: list[VastuRuleResult] = []
    for item in valid_items:
        if item.placement_zone is None or not is_valid_zone(item.placement_zone):
            raise VastuCheckerError(f"item {item.item_id} has invalid placement zone: {item.placement_zone}")
        # Facing direction is enforced in the image prompt; placement_zone cannot verify it.
        matched_rules = [
            rule
            for rule in rule_set.rules
            if rule_matches_item(rule, valid_brief, item) and rule.perspective != "orientation"
        ]
        rule_results: list[VastuRuleResult] = []
        for rule in matched_rules:
            status = rule_status_for_item(rule, item)
            result = VastuRuleResult(
                rule_id=rule.rule_id,
                item_id=item.item_id,
                object_class=normalized_item_object_class(item),
                zone=item.placement_zone,
                status=status,
                severity=SEVERITY_LABELS[rule.severity],
                weight=SEVERITY_WEIGHTS[rule.severity],
                badge=badge_for_rule(status),
                note=actionable_note(rule, item, status),
                rationale=rule.rationale,
            )
            rule_results.append(result)
            all_rule_results.append(result)
        item_results.append(
            VastuItemResult(
                item_id=item.item_id,
                title=item.title,
                object_class=normalized_item_object_class(item),
                zone=item.placement_zone,
                badge=badge_for_item(rule_results),
                notes=[result.note for result in rule_results if result.status != "pass"],
                rule_results=rule_results,
            )
        )

    score, total_weight, earned_weight = score_from_results(all_rule_results)
    notes = [
        result.note
        for result in all_rule_results
        if result.status != "pass"
    ]
    return VastuCheckResult(
        score=score,
        total_weight=total_weight,
        earned_weight=earned_weight,
        item_results=item_results,
        notes=notes,
    )
