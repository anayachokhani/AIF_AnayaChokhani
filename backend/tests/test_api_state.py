from fastapi.testclient import TestClient
from pathlib import Path

from formaos.api import main as api_main
from formaos.api.main import app, design_store, state_store
from formaos.room_state import brief_dimensions_cm, create_room_brief


def setup_function() -> None:
    state_store.clear()
    design_store.clear()
    api_main.planner_client_override = None


class FakePlannerClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, messages: list[dict[str, str]]) -> str:
        import json

        return json.dumps(self.payload)


class BrokenPlannerClient:
    def complete(self, messages: list[dict[str, str]]) -> str:
        raise ValueError("planner exploded")


def planner_payload(brief, categories: list[str] | None = None) -> dict:
    dims = brief_dimensions_cm(brief)
    categories = categories or ["sofa", "table", "rug", "lamp"]
    share = round(1 / len(categories), 4)
    return {
        "room_facts": {
            "room_type": brief.room_type,
            "width_cm": dims.width_cm,
            "depth_cm": dims.depth_cm,
            "budget_inr": brief.budget_inr,
            "style_words": brief.style_words,
        },
        "constraints": brief.constraints,
        "needs_list": [
            {
                "category": category,
                "purpose": f"{category} for the room",
                "quantity": 1,
                "priority": min(index + 1, 5),
                "budget_share": share,
                "style_tags": brief.style_words,
                "constraints": brief.constraints,
            }
            for index, category in enumerate(categories)
        ],
        "missing_questions": [],
    }


def assert_no_secret_exposure(payload: object) -> None:
    serialized = str(payload).lower()
    assert "openrouter_api_key" not in serialized
    assert "bearer " not in serialized
    assert "server-secret" not in serialized
    assert "authorization" not in serialized


def create_session(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/session", json=payload)
    assert response.status_code == 200
    return response.json()


def test_api_creates_unique_sessions_and_stores_full_brief() -> None:
    client = TestClient(app)
    brief = {
        "room_type": "living_room",
        "width": 9,
        "depth": 11,
        "units": "ft",
        "budget_inr": 60000,
        "style_words": ["warm", "wood"],
        "constraints": ["kid-friendly", "play space"],
        "vastu_enabled": True,
        "main_door_direction": "NE",
        "compass_direction": "E",
    }
    first = create_session(client, {"brief": brief})
    second = create_session(client, {"brief": {**brief, "budget_inr": 90000}})

    assert first["session_id"] != second["session_id"]
    stored = first["state"]["brief"]
    assert stored == brief
    assert first["state"]["brief_cm"] == {"width_cm": 274.3, "depth_cm": 335.3}


def test_api_session_preserves_brief_after_three_chat_messages() -> None:
    client = TestClient(app)
    body = create_session(
        client,
        {"message": "9 by 11 ft living room, Rs 60000, warm wood, kids play here"},
    )
    session_id = body["session_id"]
    original_brief = body["state"]["brief"]
    api_main.planner_client_override = FakePlannerClient(
        planner_payload(create_room_brief(**original_brief), ["table", "rug", "lamp", "planter"])
    )
    assert original_brief["room_type"] == "living_room"
    assert original_brief["width"] == 9
    assert original_brief["depth"] == 11
    assert original_brief["units"] == "ft"
    assert original_brief["budget_inr"] == 60000
    assert "warm" in original_brief["style_words"]
    assert "wood" in original_brief["style_words"]
    assert "kid-friendly" in original_brief["constraints"]
    assert "play space" in original_brief["constraints"]

    for message in ["show options", "keep it compact", "what did I ask for?"]:
        chat_response = client.post("/api/chat", json={"session_id": session_id, "message": message})
        assert chat_response.status_code == 200

    final_response = client.get(f"/api/session/{session_id}")
    assert final_response.status_code == 200
    final_state = final_response.json()["state"]
    assert final_state["brief"] == original_brief
    assert final_state["brief_cm"] == {"width_cm": 274.3, "depth_cm": 335.3}
    user_messages = [message for message in final_state["messages"] if message["role"] == "user"]
    assert len(user_messages) == 4


def test_unknown_session_returns_typed_error() -> None:
    client = TestClient(app)
    chat_response = client.post("/api/chat", json={"session_id": "missing", "message": "hello"})
    assert chat_response.status_code == 404
    assert chat_response.json()["detail"] == {"code": "not_found", "message": "session not found"}

    get_response = client.get("/api/session/missing")
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == {"code": "not_found", "message": "session not found"}


def test_two_sessions_are_isolated() -> None:
    client = TestClient(app)
    living = create_session(
        client,
        {
            "brief": {
                "room_type": "living_room",
                "width": 9,
                "depth": 11,
                "units": "ft",
                "budget_inr": 60000,
                "style_words": ["warm"],
                "constraints": ["kid-friendly"],
                "vastu_enabled": True,
                "main_door_direction": "N",
                "compass_direction": "E",
            }
        },
    )
    bedroom = create_session(
        client,
        {
            "brief": {
                "room_type": "bedroom",
                "width": 3.2,
                "depth": 4.1,
                "units": "m",
                "budget_inr": 120000,
                "style_words": ["calm"],
                "constraints": ["storage"],
                "vastu_enabled": False,
                "main_door_direction": "S",
                "compass_direction": "W",
            }
        },
    )

    client.post("/api/chat", json={"session_id": living["session_id"], "message": "do not change budget"})

    living_state = client.get(f"/api/session/{living['session_id']}").json()["state"]
    bedroom_state = client.get(f"/api/session/{bedroom['session_id']}").json()["state"]
    assert living_state["brief"]["room_type"] == "living_room"
    assert living_state["brief"]["budget_inr"] == 60000
    assert len(living_state["messages"]) == 1
    assert bedroom_state["brief"]["room_type"] == "bedroom"
    assert bedroom_state["brief"]["budget_inr"] == 120000
    assert bedroom_state["messages"] == []


def test_cors_is_enabled_for_local_frontend() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_all_api_routes_declare_response_models() -> None:
    expected = {
        ("/api/health", "GET"),
        ("/api/session", "POST"),
        ("/api/session/{session_id}", "GET"),
        ("/api/chat", "POST"),
        ("/api/design/{design_id}", "GET"),
        ("/api/design/{design_id}/revise", "POST"),
        ("/api/catalogue/search", "GET"),
        ("/api/export/{design_id}", "GET"),
    }
    found = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set())
        for method in methods:
            key = (path, method)
            if key in expected:
                assert getattr(route, "response_model", None) is not None, key
                found.add(key)
    assert found == expected


def test_frontend_never_calls_openrouter_or_sends_api_key() -> None:
    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("app").rglob("*") if path.is_file())
    lowered = frontend_text.lower()
    assert "openrouter" not in lowered
    assert "openrouter_api_key" not in lowered
    assert "authorization" not in lowered
    assert "bearer" not in lowered


def test_chat_runs_agent_loop_and_design_fetch_export_and_revise() -> None:
    client = TestClient(app)
    brief = create_room_brief(
        room_type="living room",
        width=12,
        depth=14,
        units="ft",
        budget_inr=180000,
        style_words=["warm", "wood"],
    )
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json")})

    chat_response = client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "message": "Create my design", "max_retries": 2},
    )

    assert chat_response.status_code == 200
    design = chat_response.json()["design"]
    assert_no_secret_exposure(chat_response.json())
    design_id = design["design_id"]
    assert design["status"] == "passed"
    assert design["grounder_output"]["grounded_slots"]
    assert design["critic_verdict"]["fit"]["status"] == "pass"

    get_response = client.get(f"/api/design/{design_id}")
    assert get_response.status_code == 200
    assert get_response.json()["design"]["design_id"] == design_id
    assert_no_secret_exposure(get_response.json())

    export_response = client.get(f"/api/export/{design_id}")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["design_id"] == design_id
    assert exported["selected_items"]
    assert "Amazon Berkeley Objects" in exported["attribution"]
    assert_no_secret_exposure(exported)

    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    revise_response = client.post(
        f"/api/design/{design_id}/revise",
        json={"message": "Revise with same constraints", "max_retries": 2},
    )
    assert revise_response.status_code == 200
    revised = revise_response.json()["design"]
    assert revised["status"] == "passed"
    assert revised["design_id"] == design_id
    assert_no_secret_exposure(revise_response.json())

    revised_fetch = client.get(f"/api/design/{design_id}")
    assert revised_fetch.status_code == 200
    assert revised_fetch.json()["design"]["design_id"] == design_id
    assert revised_fetch.json()["design"]["attempt_log"] == revised["attempt_log"]


def test_chat_returns_missing_api_key_error_without_backend_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)
    session = create_session(
        client,
        {
            "brief": {
                "room_type": "living_room",
                "width": 12,
                "depth": 14,
                "units": "ft",
                "budget_inr": 180000,
                "style_words": ["warm"],
                "constraints": [],
                "vastu_enabled": False,
            }
        },
    )

    response = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create design"})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "missing_api_key",
        "message": "planner API key is not configured on the backend",
    }
    assert_no_secret_exposure(response.json())


def test_retry_exhaustion_returns_stable_error_with_attempt_log() -> None:
    client = TestClient(app)
    brief = create_room_brief(room_type="living room", width=8, depth=10, units="ft", budget_inr=50)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json")})

    response = client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "message": "Create impossible design", "max_retries": 1},
    )

    assert response.status_code == 409
    body = response.json()["detail"]
    assert body["code"] == "retry_exhausted"
    assert body["message"] == "agent retry cap exhausted"
    assert body["design"]["status"] == "failed"
    assert body["design"]["attempt_log"]
    assert_no_secret_exposure(body)


def test_graph_failure_returns_stable_error_code() -> None:
    client = TestClient(app)
    brief = create_room_brief(room_type="living room", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = BrokenPlannerClient()
    session = create_session(client, {"brief": brief.model_dump(mode="json")})

    response = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create design"})

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "graph_failure",
        "message": "agent graph failed",
        "error": "ValueError",
    }


def test_catalogue_search_and_no_results_error() -> None:
    client = TestClient(app)
    response = client.get("/api/catalogue/search", params={"q": "warm sofa", "category": "sofa", "k": 3})
    assert response.status_code == 200
    assert response.json()["count"] > 0

    missing = client.get("/api/catalogue/search", params={"q": "warm sofa", "category": "not_a_category"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == {
        "code": "no_catalogue_results",
        "message": "no catalogue items matched the query",
    }


def test_invalid_brief_returns_stable_error_code() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/session",
        json={
            "brief": {
                "room_type": "living_room",
                "width": -1,
                "depth": 10,
                "units": "ft",
                "budget_inr": 50000,
            }
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_brief"
    assert response.json()["detail"]["message"] == "request validation failed"


def test_unknown_design_routes_return_typed_errors() -> None:
    client = TestClient(app)
    assert client.get("/api/design/missing").json()["detail"] == {"code": "not_found", "message": "design not found"}
    assert client.get("/api/export/missing").json()["detail"] == {"code": "not_found", "message": "design not found"}
    assert client.post("/api/design/missing/revise", json={"message": "again"}).json()["detail"] == {
        "code": "not_found",
        "message": "design not found",
    }
