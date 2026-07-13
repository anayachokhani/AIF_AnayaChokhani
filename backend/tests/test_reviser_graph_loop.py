from __future__ import annotations

import json
from pathlib import Path

import pytest

from formaos.agents.critic import CriticCheckResult, CriticVerdict
from formaos.agents.designer import PLACEMENT_HINTS
from formaos.agents.graph_loop import AgentLoopResult, run_agent_loop
from formaos.agents.planner import PlannerNeed, PlannerOutput, RoomFacts
from formaos.agents.reviser import ReviserValidationError, revise_slots
from formaos.catalogue.index_catalogue import build_index
from formaos.contracts import CheckStatus, DesignSlot
from formaos.room_state import brief_dimensions_cm, create_room_brief


CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")


class FakePlannerClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages: list[dict[str, str]]) -> str:
        return json.dumps(self.payload)


def planner_for(brief, needs: list[PlannerNeed]) -> PlannerOutput:
    dims = brief_dimensions_cm(brief)
    return PlannerOutput(
        room_facts=RoomFacts(
            room_type=brief.room_type,
            width_cm=dims.width_cm,
            depth_cm=dims.depth_cm,
            budget_inr=brief.budget_inr,
            style_words=brief.style_words,
        ),
        constraints=brief.constraints,
        needs_list=needs,
        missing_questions=[],
    )


def need(category: str, share: float, priority: int = 1) -> PlannerNeed:
    return PlannerNeed(category=category, purpose=f"{category} need", priority=priority, budget_share=share)


def failing_verdict(notes: list[str]) -> CriticVerdict:
    failed = CriticCheckResult(name="vastu", status=CheckStatus.WARN, notes=notes)
    passed = CriticCheckResult(name="fit", status=CheckStatus.PASS, notes=[])
    return CriticVerdict(
        passed=False,
        fit=passed,
        budget=CriticCheckResult(name="budget", status=CheckStatus.PASS, notes=[]),
        sourceability=CriticCheckResult(name="sourceability", status=CheckStatus.PASS, notes=[]),
        vastu=failed,
        total_price_inr=0,
        repair_notes=notes,
    )


def test_reviser_reads_critic_notes_and_changes_only_slots() -> None:
    slots = [
        DesignSlot(slot_id="slot_1_bed", category="bed", budget_share=0.5, placement_hint="NE"),
        DesignSlot(slot_id="slot_2_storage", category="storage", budget_share=0.5, placement_hint="W"),
    ]
    verdict = failing_verdict(["must: consider placing Demo bed in NE in SW."])

    output = revise_slots(slots, verdict)

    assert output.slots[0].placement_hint == "SW"
    assert output.slots[1].placement_hint == "W"
    assert output.changed_slots == ["slot_1_bed"]
    assert output.changed_items == []
    assert "Critic note" in output.notes[0]


def test_reviser_reduces_footprint_from_fit_notes() -> None:
    slot = DesignSlot(slot_id="slot_sofa", category="sofa", budget_share=1.0, target_width_cm=300, target_depth_cm=140, placement_hint="S")
    verdict = failing_verdict(
        [
            "Replace B07J2JGT7Y: width 300.0 cm exceeds 220.0 cm for slot_sofa.",
            "Replace B07J2JGT7Y: depth 140.0 cm exceeds 100.0 cm for slot_sofa.",
        ]
    )

    output = revise_slots([slot], verdict)

    assert output.slots[0].target_width_cm == 220
    assert output.slots[0].target_depth_cm == 100
    assert output.changed_slots == ["slot_sofa"]


def test_reviser_validation_errors_are_typed() -> None:
    with pytest.raises(ReviserValidationError) as exc_info:
        revise_slots([{"slot_id": "bad"}], {"passed": False})
    assert exc_info.value.code == "reviser_validation_failed"


def test_langgraph_loop_corrects_deliberately_failing_vastu_design(tmp_path: Path) -> None:
    brief = create_room_brief(
        room_type="bedroom",
        width=12,
        depth=14,
        units="ft",
        budget_inr=180000,
        style_words=["calm", "wood"],
        vastu_enabled=True,
    )
    planner = planner_for(
        brief,
        [
            need("bed", 0.45),
            need("storage", 0.25, 2),
            need("table", 0.15, 3),
            need("lamp", 0.15, 4),
        ],
    )
    chroma_path = tmp_path / "chroma"
    build_index(CATALOGUE_PATH, chroma_path)
    original_bed_hint = PLACEMENT_HINTS["bed"]
    original_table_hint = PLACEMENT_HINTS["table"]
    try:
        PLACEMENT_HINTS["bed"] = "NE"
        PLACEMENT_HINTS["table"] = "C"
        result = run_agent_loop(
            brief,
            planner_client=FakePlannerClient(planner.model_dump()),
            catalogue_path=CATALOGUE_PATH,
            chroma_path=chroma_path,
            max_retries=2,
        )
    finally:
        PLACEMENT_HINTS["bed"] = original_bed_hint
        PLACEMENT_HINTS["table"] = original_table_hint

    assert isinstance(result, AgentLoopResult)
    assert result.status == "passed"
    assert result.critic_verdict.passed is True
    assert result.retries_used >= 1
    assert any(entry.state == "revising" for entry in result.attempt_log)
    assert any("slot_1_bed" in entry.changed_slots for entry in result.attempt_log)
    bed_slot = next(slot for slot in result.grounder_output.grounded_slots if slot.slot.category == "bed")
    assert bed_slot.placement_zone == "SW"


def test_impossible_brief_fails_honestly_after_retry_cap(tmp_path: Path) -> None:
    brief = create_room_brief(
        room_type="living room",
        width=8,
        depth=10,
        units="ft",
        budget_inr=50,
        style_words=["warm"],
    )
    planner = planner_for(
        brief,
        [
            need("sofa", 0.4),
            need("table", 0.2, 2),
            need("rug", 0.2, 3),
            need("lamp", 0.2, 4),
        ],
    )
    chroma_path = tmp_path / "chroma"
    build_index(CATALOGUE_PATH, chroma_path)

    result = run_agent_loop(
        brief,
        planner_client=FakePlannerClient(planner.model_dump()),
        catalogue_path=CATALOGUE_PATH,
        chroma_path=chroma_path,
        max_retries=1,
    )

    assert result.status == "failed"
    assert result.critic_verdict.passed is False
    assert result.retries_used == 1
    assert result.grounder_output.failures
    assert any("blocked by" in note or "No deterministic slot edit" in note for entry in result.attempt_log for note in entry.notes)
