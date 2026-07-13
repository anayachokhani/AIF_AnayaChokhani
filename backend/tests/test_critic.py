from __future__ import annotations

from pathlib import Path

import pytest

from formaos.agents.critic import CriticValidationError, critique_design
from formaos.agents.grounder import GroundedSlot, GrounderOutput, SlotConstraints
from formaos.agents.pipeline import PlannerDesignerGrounderCriticResult, run_planner_designer_grounder_critic
from formaos.agents.planner import PlannerNeed, PlannerOutput, RoomFacts
from formaos.catalogue.index_catalogue import build_index
from formaos.contracts import CatalogueItem, CheckStatus, DesignSlot
from formaos.room_state import brief_dimensions_cm, create_room_brief


CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")


def item(
    item_id: str = "B089LB7TJC",
    *,
    product_type: str = "lamp",
    width_cm: float = 30,
    depth_cm: float = 30,
    price_inr: int = 2000,
    placement_zone: str = "SE",
) -> CatalogueItem:
    return CatalogueItem(
        item_id=item_id,
        title=f"{product_type} item",
        product_type=product_type,
        width_cm=width_cm,
        depth_cm=depth_cm,
        height_cm=50,
        material="wood",
        color="cream",
        price_inr=price_inr,
        source_dataset="ABO",
        placement_zone=placement_zone,
    )


def grounded_slot(
    selected: CatalogueItem,
    *,
    category: str | None = None,
    max_width_cm: float = 100,
    max_depth_cm: float = 100,
    max_price_inr: int = 50000,
    placement_zone: str | None = None,
) -> GroundedSlot:
    resolved_category = category or selected.product_type
    resolved_zone = placement_zone or selected.placement_zone or "C"
    return GroundedSlot(
        slot=DesignSlot(slot_id=f"slot_{resolved_category}", category=resolved_category, budget_share=1.0, placement_hint=resolved_zone),
        placement_zone=resolved_zone,
        constraints=SlotConstraints(max_width_cm=max_width_cm, max_depth_cm=max_depth_cm, max_price_inr=max_price_inr),
        selected_item=selected.model_copy(update={"placement_zone": resolved_zone}),
        alternatives=[
            selected.model_copy(update={"item_id": "B07QB7HXXF", "placement_zone": resolved_zone}),
            selected.model_copy(update={"item_id": "B07HK85JKQ", "placement_zone": resolved_zone}),
        ],
    )


def test_critic_passes_valid_non_vastu_plan() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    grounded = GrounderOutput(grounded_slots=[grounded_slot(item())])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.passed is True
    assert verdict.fit.status == CheckStatus.PASS
    assert verdict.budget.status == CheckStatus.PASS
    assert verdict.sourceability.status == CheckStatus.PASS
    assert verdict.vastu.status == CheckStatus.SKIPPED
    assert verdict.total_price_inr == 2000


def test_critic_catches_oversized_sofa_with_repair_note() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=120000)
    oversized = item("B07J2JGT7Y", product_type="sofa", width_cm=300, depth_cm=150, price_inr=50000, placement_zone="S")
    grounded = GrounderOutput(grounded_slots=[grounded_slot(oversized, max_width_cm=220, max_depth_cm=100, placement_zone="S")])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.passed is False
    assert verdict.fit.status == CheckStatus.FAIL
    assert any("width 300.0 cm exceeds 220.0 cm" in note for note in verdict.fit.notes)
    assert any("depth 150.0 cm exceeds 100.0 cm" in note for note in verdict.fit.notes)


def test_critic_catches_over_budget_plan_with_exact_repair_note() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=1000)
    grounded = GrounderOutput(grounded_slots=[grounded_slot(item(price_inr=2500))])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.budget.status == CheckStatus.FAIL
    assert verdict.total_price_inr == 2500
    assert any("Reduce total price by at least INR 1500" in note for note in verdict.budget.notes)


def test_critic_catches_fake_item_id() -> None:
    brief = create_room_brief(room_type="living room", width=10, depth=12, units="ft", budget_inr=85000)
    grounded = GrounderOutput(grounded_slots=[grounded_slot(item("FAKE-ITEM-123"))])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.sourceability.status == CheckStatus.FAIL
    assert any("FAKE-ITEM-123" in note and "curated catalogue" in note for note in verdict.sourceability.notes)


def test_critic_calls_vastu_only_when_requested_and_catches_violation() -> None:
    brief = create_room_brief(
        room_type="bedroom",
        width=10,
        depth=12,
        units="ft",
        budget_inr=120000,
        vastu_enabled=True,
    )
    bed = item("B075SYQ79F", product_type="bed", width_cm=180, depth_cm=210, price_inr=45000, placement_zone="NE")
    grounded = GrounderOutput(grounded_slots=[grounded_slot(bed, category="bed", max_width_cm=220, max_depth_cm=230, placement_zone="NE")])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.vastu.status == CheckStatus.FAIL
    assert verdict.vastu_result is not None
    assert any("consider placing" in note for note in verdict.vastu.notes)
    assert verdict.passed is False


def test_critic_skips_vastu_when_not_requested_even_with_bad_zone() -> None:
    brief = create_room_brief(room_type="bedroom", width=10, depth=12, units="ft", budget_inr=120000, vastu_enabled=False)
    bed = item("B075SYQ79F", product_type="bed", width_cm=180, depth_cm=210, price_inr=45000, placement_zone="NE")
    grounded = GrounderOutput(grounded_slots=[grounded_slot(bed, category="bed", max_width_cm=220, max_depth_cm=230, placement_zone="NE")])

    verdict = critique_design(brief, grounded, catalogue_path=CATALOGUE_PATH)

    assert verdict.vastu.status == CheckStatus.SKIPPED
    assert verdict.vastu_result is None


def test_critic_validation_errors_are_typed() -> None:
    with pytest.raises(CriticValidationError) as exc_info:
        critique_design({"room_type": "living_room"}, {"grounded_slots": []}, catalogue_path=CATALOGUE_PATH)

    assert exc_info.value.code == "critic_validation_failed"


class FakePlannerClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages: list[dict[str, str]]) -> str:
        import json

        return json.dumps(self.payload)


def test_full_pipeline_runs_critic(tmp_path: Path) -> None:
    brief = create_room_brief(
        room_type="living room",
        width=12,
        depth=14,
        units="ft",
        budget_inr=140000,
        style_words=["warm", "wood"],
    )
    dims = brief_dimensions_cm(brief)
    planner = PlannerOutput(
        room_facts=RoomFacts(
            room_type=brief.room_type,
            width_cm=dims.width_cm,
            depth_cm=dims.depth_cm,
            budget_inr=brief.budget_inr,
            style_words=brief.style_words,
        ),
        constraints=brief.constraints,
        needs_list=[
            PlannerNeed(category="sofa", purpose="primary seating", priority=1, budget_share=0.45),
            PlannerNeed(category="table", purpose="coffee surface", priority=2, budget_share=0.2),
            PlannerNeed(category="rug", purpose="soft zone", priority=3, budget_share=0.2),
            PlannerNeed(category="lamp", purpose="warm lighting", priority=4, budget_share=0.15),
        ],
        missing_questions=[],
    )
    chroma_path = tmp_path / "chroma"
    build_index(CATALOGUE_PATH, chroma_path)

    result = run_planner_designer_grounder_critic(
        brief,
        planner_client=FakePlannerClient(planner.model_dump()),
        catalogue_path=CATALOGUE_PATH,
        chroma_path=chroma_path,
    )

    assert isinstance(result, PlannerDesignerGrounderCriticResult)
    assert result.critic_verdict.fit.status == CheckStatus.PASS
    assert result.critic_verdict.budget.status == CheckStatus.PASS
    assert result.critic_verdict.sourceability.status == CheckStatus.PASS
    assert result.critic_verdict.vastu.status == CheckStatus.SKIPPED
