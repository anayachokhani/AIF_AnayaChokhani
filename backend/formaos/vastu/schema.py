from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import AnyUrl, BaseModel, Field, ValidationError, field_validator

from formaos.contracts import Direction


Severity = Literal["info", "warn", "critical"]
Perspective = Literal["placement", "orientation", "color", "clearance"]
RoomType = Literal["any", "living_room", "bedroom", "study", "kitchen"]
ALLOWED_OBJECT_CLASSES = {
    "bed",
    "cabinet",
    "central_clearance",
    "chair",
    "desk",
    "heavy_furniture",
    "lamp",
    "loveseat",
    "mirror",
    "planter",
    "rug",
    "sofa",
    "storage",
    "stove",
    "table",
    "water_feature",
}
ALLOWED_COLOR_PATTERN = re.compile(r"^[a-z][a-z ]*$")
REQUIRED_RULE_FIELDS = [
    "rule_id",
    "perspective",
    "room_type",
    "object_class",
    "preferred_zones",
    "avoided_zones",
    "preferred_colors",
    "avoided_colors",
    "severity",
    "rationale",
    "source_urls",
    "confidence",
]


class VastuRule(BaseModel):
    rule_id: str = Field(..., pattern=r"^VR-[0-9]{3}$")
    perspective: Perspective
    room_type: RoomType
    object_class: str = Field(..., min_length=1)
    preferred_zones: list[Direction] = Field(default_factory=list)
    avoided_zones: list[Direction] = Field(default_factory=list)
    preferred_colors: list[str] = Field(default_factory=list)
    avoided_colors: list[str] = Field(default_factory=list)
    severity: Severity
    rationale: str = Field(..., min_length=24)
    source_urls: list[AnyUrl] = Field(..., min_length=1)
    confidence: float = Field(..., ge=0, le=1)

    @field_validator("object_class")
    @classmethod
    def object_class_must_be_normalized(cls, value: str) -> str:
        if value != value.strip().lower() or not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError("object_class must be normalized lower snake case")
        if value not in ALLOWED_OBJECT_CLASSES:
            raise ValueError(f"unsupported object_class: {value}")
        return value

    @field_validator("preferred_zones", "avoided_zones")
    @classmethod
    def zones_must_not_repeat(cls, zones: list[Direction]) -> list[Direction]:
        if len(zones) != len(set(zones)):
            raise ValueError("zones must be unique")
        return zones

    @field_validator("preferred_colors", "avoided_colors")
    @classmethod
    def colors_must_be_normalized(cls, colors: list[str]) -> list[str]:
        if any(color != color.strip().lower() or not ALLOWED_COLOR_PATTERN.fullmatch(color) for color in colors):
            raise ValueError("colors must be normalized lowercase names")
        if len(colors) != len(set(colors)):
            raise ValueError("colors must be unique")
        return colors


class VastuRuleSet(BaseModel):
    version: str = Field(default="v1")
    guidance_mode: Literal["opt_in"] = "opt_in"
    disclaimer: str = Field(..., min_length=40)
    rules: list[VastuRule] = Field(..., min_length=25, max_length=40)

    @field_validator("rules")
    @classmethod
    def rule_ids_must_be_unique(cls, rules: list[VastuRule]) -> list[VastuRule]:
        ids = [rule.rule_id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule IDs must be unique")
        return rules


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def rule_from_csv_row(row: dict[str, str]) -> VastuRule:
    return VastuRule(
        rule_id=row["rule_id"],
        perspective=row["perspective"],
        room_type=row["room_type"],
        object_class=row["object_class"],
        preferred_zones=split_list(row.get("preferred_zones", "")),
        avoided_zones=split_list(row.get("avoided_zones", "")),
        preferred_colors=split_list(row.get("preferred_colors", "")),
        avoided_colors=split_list(row.get("avoided_colors", "")),
        severity=row["severity"],
        rationale=row["rationale"],
        source_urls=split_list(row.get("source_urls", "")),
        confidence=float(row["confidence"]),
    )


def load_seed_csv(path: Path) -> list[VastuRule]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [rule_from_csv_row(row) for row in csv.DictReader(handle)]


def load_rule_set(path: Path) -> VastuRuleSet:
    return VastuRuleSet.model_validate_json(path.read_text(encoding="utf-8"))


def build_rule_set(seed_path: Path) -> VastuRuleSet:
    return VastuRuleSet(
        disclaimer=(
            "Vastu rules in FormaOS are optional traditional guidance for users who request it; "
            "they are not scientific, architectural, safety, legal, or guaranteed outcome claims."
        ),
        rules=load_seed_csv(seed_path),
    )


def write_rule_set(seed_path: Path, output_path: Path) -> VastuRuleSet:
    rule_set = build_rule_set(seed_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rule_set.model_dump_json(indent=2), encoding="utf-8")
    return rule_set


def validate_rule_file(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_rules = payload.get("rules", [])
    rule_ids = [rule.get("rule_id") for rule in raw_rules if isinstance(rule, dict)]
    duplicate_ids = sorted({rule_id for rule_id in rule_ids if rule_ids.count(rule_id) > 1})
    missing_fields: list[dict[str, object]] = []
    invalid_room_types = 0
    invalid_object_classes = 0
    invalid_zones = 0
    invalid_colors = 0
    missing_rationales = 0
    missing_source_urls = 0
    invalid_confidence_values = 0
    invalid_severity_values = 0
    valid_zones = {"NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"}
    valid_room_types = {"any", "living_room", "bedroom", "study", "kitchen"}
    valid_severities = {"info", "warn", "critical"}

    for index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            missing_fields.append({"index": index, "fields": REQUIRED_RULE_FIELDS})
            continue
        missing = [field for field in REQUIRED_RULE_FIELDS if field not in rule]
        if missing:
            missing_fields.append({"rule_id": rule.get("rule_id", f"index_{index}"), "fields": missing})
        if rule.get("room_type") not in valid_room_types:
            invalid_room_types += 1
        object_class = rule.get("object_class")
        if object_class not in ALLOWED_OBJECT_CLASSES:
            invalid_object_classes += 1
        for field in ["preferred_zones", "avoided_zones"]:
            zones = rule.get(field, [])
            if not isinstance(zones, list) or any(zone not in valid_zones for zone in zones):
                invalid_zones += 1
        for field in ["preferred_colors", "avoided_colors"]:
            colors = rule.get(field, [])
            if not isinstance(colors, list) or any(
                not isinstance(color, str) or not ALLOWED_COLOR_PATTERN.fullmatch(color) for color in colors
            ):
                invalid_colors += 1
        if not str(rule.get("rationale", "")).strip():
            missing_rationales += 1
        if not rule.get("source_urls"):
            missing_source_urls += 1
        confidence = rule.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            invalid_confidence_values += 1
        if rule.get("severity") not in valid_severities:
            invalid_severity_values += 1

    VastuRuleSet.model_validate(payload)
    return {
        "total_rules": len(raw_rules),
        "duplicate_rule_ids": duplicate_ids,
        "missing_fields": missing_fields,
        "invalid_room_types": invalid_room_types,
        "invalid_object_classes": invalid_object_classes,
        "invalid_zones": invalid_zones,
        "invalid_colors": invalid_colors,
        "missing_rationales": missing_rationales,
        "missing_source_urls": missing_source_urls,
        "invalid_confidence_values": invalid_confidence_values,
        "invalid_severity_values": invalid_severity_values,
    }


def write_validation_report(rule_path: Path, report_path: Path) -> dict[str, object]:
    report = validate_rule_file(rule_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vastu seed CSV and write JSON rules.")
    parser.add_argument("--seeds", type=Path, default=Path("data/vastu/seeds.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/vastu/vastu_rules_v1.json"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/metrics/vastu_rules_validation.json"))
    args = parser.parse_args()
    try:
        rule_set = write_rule_set(args.seeds, args.output)
        report = write_validation_report(args.output, args.report)
    except (ValidationError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {"status": "pass", "rules": len(rule_set.rules), "output": str(args.output), "report": report},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
