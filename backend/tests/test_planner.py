import json
import os

import pytest

from formaos.agents.planner import (
    OpenRouterPlannerClient,
    PlannerOutput,
    PlannerValidationError,
    build_planner_prompt,
    plan_room,
)
from formaos.room_state import create_room_brief


class FakePlannerClient:
    def __init__(self, responses: list[dict | str]) -> None:
        self.responses = responses
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, str):
            return response
        return json.dumps(response)


def planner_payload(brief, needs: list[dict], missing_questions: list[str] | None = None) -> dict:
    width_cm = round(brief.width * 30.48, 1) if brief.units == "ft" else round(brief.width * 100, 1)
    depth_cm = round(brief.depth * 30.48, 1) if brief.units == "ft" else round(brief.depth * 100, 1)
    if brief.units == "cm":
        width_cm = round(brief.width, 1)
        depth_cm = round(brief.depth, 1)
    return {
        "room_facts": {
            "room_type": brief.room_type,
            "width_cm": width_cm,
            "depth_cm": depth_cm,
            "budget_inr": brief.budget_inr,
            "style_words": brief.style_words,
        },
        "constraints": brief.constraints,
        "needs_list": needs,
        "missing_questions": missing_questions or [],
    }


def need(category: str, budget_share: float, priority: int = 1) -> dict:
    return {
        "category": category,
        "purpose": f"{category} for the room",
        "quantity": 1,
        "priority": priority,
        "max_width_cm": 220,
        "max_depth_cm": 110,
        "budget_share": budget_share,
        "style_tags": ["warm", "wood"],
        "constraints": ["kid-friendly"],
    }


def test_normal_living_room_fixture_returns_typed_needs() -> None:
    brief = create_room_brief(
        room_type="living room",
        width=9,
        depth=11,
        units="ft",
        budget_inr=60000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    client = FakePlannerClient(
        [planner_payload(brief, [need("sofa", 0.42), need("table", 0.18, 2), need("rug", 0.12, 3), need("storage", 0.2, 4)])]
    )
    output = plan_room(brief, client)
    assert isinstance(output, PlannerOutput)
    assert output.room_facts.room_type == "living_room"
    assert output.room_facts.budget_inr == 60000
    assert [item.category for item in output.needs_list] == ["sofa", "table", "rug", "storage"]
    assert output.needs_list[0].constraints == ["kid-friendly"]


def test_tiny_bedroom_fixture_returns_practical_compact_needs() -> None:
    brief = create_room_brief(
        room_type="bedroom",
        width=2.5,
        depth=3.0,
        units="m",
        budget_inr=70000,
        style_words=["calm", "compact"],
        constraints=["storage"],
    )
    client = FakePlannerClient([planner_payload(brief, [need("bed", 0.48), need("storage", 0.25, 2), need("lamp", 0.08, 3)])])
    output = plan_room(brief, client)
    assert output.room_facts.width_cm == 250
    assert output.room_facts.depth_cm == 300
    assert [item.category for item in output.needs_list] == ["bed", "storage", "lamp"]


def test_vague_budget_fixture_uses_default_budget_and_missing_question() -> None:
    brief = create_room_brief(room_type="study", style_words=["minimal", "focused"])
    client = FakePlannerClient(
        [planner_payload(brief, [need("desk", 0.42), need("chair", 0.25), need("lamp", 0.1)], ["Confirm final budget ceiling."])]
    )
    output = plan_room(brief, client)
    assert isinstance(output.missing_questions, list)
    assert output.room_facts.budget_inr == 60000
    assert "Confirm final budget ceiling." in output.missing_questions
    assert [item.category for item in output.needs_list] == ["desk", "chair", "lamp"]


def test_planner_retries_once_after_schema_invalid_model_json() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    client = FakePlannerClient(
        [
            {"room_facts": {"room_type": "living_room"}},
            planner_payload(brief, [need("sofa", 0.5), need("table", 0.2)]),
        ]
    )
    output = plan_room(brief, client)
    assert output.needs_list[0].category == "sofa"
    assert len(client.messages) == 2
    assert "Previous response failed validation" in client.messages[1][1]["content"]


def test_malformed_json_response_triggers_retry() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    client = FakePlannerClient(
        [
            "{not valid json",
            planner_payload(brief, [need("sofa", 0.5), need("table", 0.2)]),
        ]
    )
    output = plan_room(brief, client)
    assert isinstance(output, PlannerOutput)
    assert [item.category for item in output.needs_list] == ["sofa", "table"]
    assert len(client.messages) == 2
    assert "Previous response failed validation" in client.messages[1][1]["content"]


def test_retry_failure_returns_typed_validation_error_not_invalid_data() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    client = FakePlannerClient(["{not valid json", "{still not valid json"])
    with pytest.raises(PlannerValidationError) as exc_info:
        plan_room(brief, client)
    assert exc_info.value.code == "planner_validation_failed"
    assert exc_info.value.raw_response == "{still not valid json"
    assert len(client.messages) == 2


def test_planner_rejects_changed_room_facts_after_retry_with_typed_error() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    changed = planner_payload(brief, [need("sofa", 0.5), need("table", 0.2)])
    changed["room_facts"]["budget_inr"] = 1
    client = FakePlannerClient([changed, changed])
    with pytest.raises(PlannerValidationError) as exc_info:
        plan_room(brief, client)
    assert exc_info.value.code == "planner_validation_failed"
    assert "budget changed" in str(exc_info.value.original_error)


def test_openrouter_client_requires_server_side_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="missing_api_key"):
        OpenRouterPlannerClient()


def test_openrouter_client_sends_server_side_api_key(monkeypatch) -> None:
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("formaos.agents.planner.httpx.post", fake_post)
    client = OpenRouterPlannerClient(api_key="server-secret", model="test/model", timeout=3)
    client.complete([{"role": "user", "content": "Return JSON"}])
    assert captured["headers"]["Authorization"] == "Bearer server-secret"
    assert captured["json"]["model"] == "test/model"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_prompt_requests_strict_json_and_allowed_categories() -> None:
    brief = create_room_brief(room_type="living room", width=9, depth=11, units="ft", budget_inr=60000)
    messages = build_planner_prompt(brief)
    assert "Return only strict JSON" in messages[0]["content"]
    assert "Allowed categories" in messages[0]["content"]
    assert "RoomBrief" in messages[1]["content"]


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY is not set; skipping live OpenRouter integration test.",
)
def test_openrouter_integration_when_api_key_present() -> None:
    brief = create_room_brief(
        room_type="living room",
        width=9,
        depth=11,
        units="ft",
        budget_inr=60000,
        style_words=["warm", "wood"],
        constraints=["kid-friendly"],
    )
    output = plan_room(brief)
    assert isinstance(output, PlannerOutput)
    assert output.room_facts.room_type == brief.room_type
    assert output.room_facts.budget_inr == brief.budget_inr
    assert output.needs_list
