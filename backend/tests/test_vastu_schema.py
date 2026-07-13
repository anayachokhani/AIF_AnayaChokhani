from __future__ import annotations

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from formaos.room_state import create_room_brief
from formaos.vastu.schema import VastuRule, VastuRuleSet, build_rule_set, load_rule_set, validate_rule_file


SEED_PATH = Path("data/vastu/seeds.csv")
RULES_PATH = Path("data/vastu/vastu_rules_v1.json")
README_PATH = Path("data/vastu/README.md")
REPORT_PATH = Path("artifacts/metrics/vastu_rules_validation.json")


def valid_rule_payload(**overrides):
    payload = {
        "rule_id": "VR-999",
        "perspective": "placement",
        "room_type": "living_room",
        "object_class": "sofa",
        "preferred_zones": ["S", "W"],
        "avoided_zones": ["NE"],
        "preferred_colors": ["earth", "cream"],
        "avoided_colors": ["black"],
        "severity": "warn",
        "rationale": "Traditional guidance keeps heavier seating on south or west walls.",
        "source_urls": ["https://en.wikipedia.org/wiki/Vastu_shastra"],
        "confidence": 0.6,
    }
    payload.update(overrides)
    return payload


def test_seed_csv_contains_required_rule_count_and_fields() -> None:
    with SEED_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert 25 <= len(rows) <= 40
    assert len({row["rule_id"] for row in rows}) == len(rows)
    for row in rows:
        assert row["rule_id"]
        assert row["perspective"]
        assert row["room_type"]
        assert row["object_class"]
        assert row["severity"] in {"info", "warn", "critical"}
        assert row["rationale"]
        assert row["source_urls"]
        assert float(row["confidence"]) > 0


def test_generated_vastu_json_validates_against_schema() -> None:
    rule_set = load_rule_set(RULES_PATH)

    assert isinstance(rule_set, VastuRuleSet)
    assert rule_set.version == "v1"
    assert rule_set.guidance_mode == "opt_in"
    assert len(rule_set.rules) == 30
    assert all(rule.rationale for rule in rule_set.rules)
    assert all(rule.source_urls for rule in rule_set.rules)
    assert all(0 <= rule.confidence <= 1 for rule in rule_set.rules)


def test_seed_csv_and_json_represent_same_rules() -> None:
    from_csv = build_rule_set(SEED_PATH)
    from_json = load_rule_set(RULES_PATH)

    assert from_json.model_dump(mode="json") == from_csv.model_dump(mode="json")


def test_validation_report_has_zero_issue_counts() -> None:
    report = validate_rule_file(RULES_PATH)

    assert report["total_rules"] == 30
    assert report["duplicate_rule_ids"] == []
    assert report["missing_fields"] == []
    assert report["invalid_room_types"] == 0
    assert report["invalid_object_classes"] == 0
    assert report["invalid_zones"] == 0
    assert report["invalid_colors"] == 0
    assert report["missing_rationales"] == 0
    assert report["missing_source_urls"] == 0
    assert report["invalid_confidence_values"] == 0
    assert report["invalid_severity_values"] == 0


def test_validation_report_file_exists_and_matches_schema_output() -> None:
    assert REPORT_PATH.exists()
    assert validate_rule_file(RULES_PATH)["total_rules"] == 30


def test_duplicate_rule_ids_are_rejected() -> None:
    rule = VastuRule.model_validate(valid_rule_payload())
    with pytest.raises(ValidationError, match="rule IDs must be unique"):
        VastuRuleSet(disclaimer="Optional traditional guidance only for enabled Vastu checks.", rules=[rule] * 25)


def test_required_field_validation_rejects_missing_rationale() -> None:
    payload = valid_rule_payload()
    del payload["rationale"]
    with pytest.raises(ValidationError):
        VastuRule.model_validate(payload)


def test_invalid_room_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VastuRule.model_validate(valid_rule_payload(room_type="bathroom"))


def test_invalid_object_class_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported object_class"):
        VastuRule.model_validate(valid_rule_payload(object_class="television"))


def test_invalid_zone_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VastuRule.model_validate(valid_rule_payload(preferred_zones=["UP"]))


def test_invalid_color_is_rejected() -> None:
    with pytest.raises(ValidationError, match="colors must be normalized"):
        VastuRule.model_validate(valid_rule_payload(preferred_colors=["Warm White"]))


def test_invalid_confidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VastuRule.model_validate(valid_rule_payload(confidence=1.5))


def test_invalid_severity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VastuRule.model_validate(valid_rule_payload(severity="blocker"))


def test_vastu_readme_states_opt_in_traditional_guidance() -> None:
    content = README_PATH.read_text(encoding="utf-8").lower()

    assert "opt-in" in content
    assert "traditional guidance" in content
    assert "must not apply" in content
    assert "explicitly enables" in content


def test_room_brief_defaults_do_not_enable_vastu_rules() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)

    assert brief.vastu_enabled is False
