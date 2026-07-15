from fastapi.testclient import TestClient
from pathlib import Path
import pytest

from formaos.api import main as api_main
from formaos.api.main import FileAuthStore, FileDesignStore, app, state_store
from formaos.room_state import brief_dimensions_cm, create_room_brief


@pytest.fixture(autouse=True)
def isolated_api_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMAOS_REQUIRE_AUTH", "0")
    monkeypatch.setattr(api_main, "design_store", FileDesignStore(tmp_path / "designs.json"))
    monkeypatch.setattr(api_main, "auth_store", FileAuthStore(tmp_path / "accounts.json"))
    state_store.clear()
    api_main.session_users.clear()
    api_main.session_projects.clear()
    api_main.planner_client_override = None
    yield
    state_store.clear()
    api_main.session_users.clear()
    api_main.session_projects.clear()
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
    if categories is None:
        categories = {
            "bedroom": ["bed", "storage", "table", "rug", "lamp", "chair", "mirror", "planter"],
            "study": ["desk", "chair", "storage", "rug", "lamp", "table", "mirror", "planter"],
        }.get(brief.room_type, ["sofa", "chair", "table", "rug", "storage", "lamp", "mirror", "planter"])
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
        ("/api/auth/signup", "POST"),
        ("/api/auth/login", "POST"),
        ("/api/auth/me", "GET"),
        ("/api/auth/logout", "POST"),
        ("/api/session", "POST"),
        ("/api/session/{session_id}", "GET"),
        ("/api/chat", "POST"),
        ("/api/concept-image", "POST"),
        ("/api/designs", "GET"),
        ("/api/projects/{project_id}", "DELETE"),
        ("/api/design/{design_id}", "GET"),
        ("/api/design/{design_id}/revise", "POST"),
        ("/api/design/{design_id}/select-item", "POST"),
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


def test_account_signup_login_and_logout_use_server_session_cookie() -> None:
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={"name": "Anaya Homeowner", "email": "anaya@example.com", "password": "a-secure-password"},
    )
    assert signup.status_code == 200
    assert signup.json()["user"]["email"] == "anaya@example.com"
    assert api_main.AUTH_COOKIE_NAME in signup.cookies
    assert "httponly" in signup.headers["set-cookie"].lower()
    assert "a-secure-password" not in api_main.auth_store.path.read_text(encoding="utf-8")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["name"] == "Anaya Homeowner"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    bad_login = client.post("/api/auth/login", json={"email": "anaya@example.com", "password": "wrong-password"})
    assert bad_login.status_code == 401
    login = client.post("/api/auth/login", json={"email": "anaya@example.com", "password": "a-secure-password"})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_account_password_and_session_survive_store_reload(tmp_path) -> None:
    store_path = tmp_path / "auth" / "accounts.json"
    store = FileAuthStore(store_path)
    created = store.create_user("Persistent Homeowner", "persistent@example.com", "a-secure-password")
    token = store.create_session(created["id"])

    reloaded = FileAuthStore(store_path)

    assert reloaded.authenticate("persistent@example.com", "a-secure-password") == created
    assert reloaded.user_for_token(token) == created
    assert store_path.stat().st_mode & 0o777 == 0o600
    assert "a-secure-password" not in store_path.read_text(encoding="utf-8")


def test_furniture_alternative_is_saved_rechecked_and_owner_scoped() -> None:
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={"name": "Anaya", "email": "anaya@example.com", "password": "a-secure-password"},
    )
    user_id = signup.json()["user"]["id"]
    brief = create_room_brief(room_type="living room", width=12, depth=14, units="ft", budget_inr=180000, style_words=["modern"])
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "project_id": "project-living"})
    generated = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create my room"}).json()["design"]
    target_slot = next(slot for slot in generated["grounder_output"]["grounded_slots"] if slot["alternatives"])
    replacement = target_slot["alternatives"][0]

    selected = client.post(
        f"/api/design/{generated['design_id']}/select-item",
        json={"slot_id": target_slot["slot"]["slot_id"], "item_id": replacement["item_id"]},
    )
    assert selected.status_code == 200
    updated = selected.json()["design"]
    updated_slot = next(slot for slot in updated["grounder_output"]["grounded_slots"] if slot["slot"]["slot_id"] == target_slot["slot"]["slot_id"])
    assert updated_slot["selected_item"]["item_id"] == replacement["item_id"]
    selected_items = [slot["selected_item"] for slot in updated["grounder_output"]["grounded_slots"] if slot.get("selected_item")]
    assert updated["critic_verdict"]["total_price_inr"] == sum(item["price_inr"] for item in selected_items)
    assert updated["user_id"] == user_id
    assert updated["chat_messages"][-1]["role"] == "assistant"

    other = TestClient(app)
    other.post("/api/auth/signup", json={"name": "Other", "email": "other@example.com", "password": "another-password"})
    assert other.get(f"/api/design/{generated['design_id']}").status_code == 404


def test_project_delete_removes_all_design_versions_and_chat_sessions_for_owner() -> None:
    client = TestClient(app)
    client.post(
        "/api/auth/signup",
        json={"name": "Anaya", "email": "anaya@example.com", "password": "a-secure-password"},
    )
    brief = create_room_brief(room_type="living_room", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    deleted_sessions: list[str] = []
    deleted_design_ids: list[str] = []
    for _ in range(2):
        session = create_session(
            client,
            {"brief": brief.model_dump(mode="json"), "project_id": "project-to-delete"},
        )
        deleted_sessions.append(session["session_id"])
        generated = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "Create design"},
        ).json()["design"]
        deleted_design_ids.append(generated["design_id"])

    kept_session = create_session(
        client,
        {"brief": brief.model_dump(mode="json"), "project_id": "project-to-keep"},
    )
    kept_design = client.post(
        "/api/chat",
        json={"session_id": kept_session["session_id"], "message": "Create another design"},
    ).json()["design"]

    response = client.delete("/api/projects/project-to-delete")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "deleted_designs": 2}
    assert all(api_main.design_store.get(design_id) is None for design_id in deleted_design_ids)
    assert all(state_store.get(session_id) is None for session_id in deleted_sessions)
    assert api_main.design_store.get(kept_design["design_id"]) is not None
    assert client.delete("/api/projects/project-to-delete").status_code == 404

    other = TestClient(app)
    other.post(
        "/api/auth/signup",
        json={"name": "Other", "email": "other@example.com", "password": "another-password"},
    )
    assert other.delete("/api/projects/project-to-keep").status_code == 404


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
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "user_id": "homeowner-anaya"})

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
    assert exported["project_name"]
    assert exported["concept_image_data_url"] is None
    assert exported["source_image_data_url"] is None
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

    refresh_response = client.post(
        f"/api/design/{design_id}/revise",
        json={"message": "Refresh furniture matches", "refresh_products": True},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()["design"]
    for grounded_slot in refreshed["grounder_output"]["grounded_slots"]:
        if grounded_slot["selected_item"]:
            assert grounded_slot["selected_item"]["product_type"] == grounded_slot["slot"]["category"]
    assert "refreshed every furniture match" in refreshed["chat_messages"][-1]["content"]


def test_saved_designs_are_listed_and_survive_store_reload(tmp_path, monkeypatch) -> None:
    store_path = tmp_path / "designs.json"
    monkeypatch.setattr(api_main, "design_store", FileDesignStore(store_path))
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
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "user_id": "homeowner-anaya"})

    chat_response = client.post(
        "/api/chat",
        json={"session_id": session["session_id"], "message": "Create my design", "max_retries": 2},
    )
    assert chat_response.status_code == 200
    design_id = chat_response.json()["design"]["design_id"]
    assert chat_response.json()["design"]["user_id"] == "homeowner-anaya"

    list_response = client.get("/api/designs", params={"user_id": "homeowner-anaya"})
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["count"] == 1
    assert listed["designs"][0]["design_id"] == design_id
    assert listed["designs"][0]["user_id"] == "homeowner-anaya"
    assert listed["designs"][0]["item_count"] > 0

    other_user_response = client.get("/api/designs", params={"user_id": "homeowner-someone-else"})
    assert other_user_response.status_code == 200
    assert other_user_response.json() == {"designs": [], "count": 0}

    monkeypatch.setattr(api_main, "design_store", FileDesignStore(store_path))
    api_main.state_store.clear()

    get_response = client.get(f"/api/design/{design_id}")
    assert get_response.status_code == 200
    assert get_response.json()["design"]["room_brief"]["budget_inr"] == 180000

    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    revise_response = client.post(
        f"/api/design/{design_id}/revise",
        json={"message": "Revise after reload", "max_retries": 2},
    )
    assert revise_response.status_code == 200
    assert revise_response.json()["design"]["design_id"] == design_id
    assert revise_response.json()["design"]["user_id"] == "homeowner-anaya"


def test_saved_designs_are_scoped_by_project_and_keep_project_metadata(tmp_path, monkeypatch) -> None:
    store_path = tmp_path / "designs.json"
    monkeypatch.setattr(api_main, "design_store", FileDesignStore(store_path))
    client = TestClient(app)
    living_brief = create_room_brief(room_type="living_room", width=12, depth=14, units="ft", budget_inr=180000)
    bedroom_brief = create_room_brief(room_type="bedroom", width=10, depth=11, units="ft", budget_inr=220000)

    api_main.planner_client_override = FakePlannerClient(planner_payload(living_brief))
    living_session = create_session(
        client,
        {
            "brief": living_brief.model_dump(mode="json"),
            "user_id": "homeowner-anaya",
            "project_id": "project-living",
            "project_name": "Living Room Refresh",
        },
    )
    living_response = client.post("/api/chat", json={"session_id": living_session["session_id"], "message": "Create living room"})
    assert living_response.status_code == 200

    api_main.planner_client_override = FakePlannerClient(planner_payload(bedroom_brief))
    bedroom_session = create_session(
        client,
        {
            "brief": bedroom_brief.model_dump(mode="json"),
            "user_id": "homeowner-anaya",
            "project_id": "project-bedroom",
            "project_name": "Bedroom Storage",
        },
    )
    bedroom_response = client.post("/api/chat", json={"session_id": bedroom_session["session_id"], "message": "Create bedroom"})
    assert bedroom_response.status_code == 200

    all_response = client.get("/api/designs", params={"user_id": "homeowner-anaya"})
    assert all_response.status_code == 200
    assert all_response.json()["count"] == 2

    living_list = client.get("/api/designs", params={"user_id": "homeowner-anaya", "project_id": "project-living"})
    assert living_list.status_code == 200
    assert living_list.json()["count"] == 1
    assert living_list.json()["designs"][0]["project_id"] == "project-living"
    assert living_list.json()["designs"][0]["project_name"] == "Living Room Refresh"
    assert living_list.json()["designs"][0]["room_type"] == "living_room"

    bedroom_list = client.get("/api/designs", params={"user_id": "homeowner-anaya", "project_id": "project-bedroom"})
    assert bedroom_list.status_code == 200
    assert bedroom_list.json()["count"] == 1
    assert bedroom_list.json()["designs"][0]["project_id"] == "project-bedroom"
    assert bedroom_list.json()["designs"][0]["room_type"] == "bedroom"


def test_duplicate_generations_in_one_project_are_consolidated_as_versions() -> None:
    client = TestClient(app)
    brief = create_room_brief(room_type="bedroom", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))

    first_session = create_session(client, {
        "brief": brief.model_dump(mode="json"),
        "user_id": "homeowner-anaya",
        "project_id": "project-bedroom",
        "project_name": "Bedroom",
    })
    first = client.post("/api/chat", json={"session_id": first_session["session_id"], "message": "First version"}).json()["design"]
    first["source_images"] = ["data:image/jpeg;base64,c291cmNl"]
    first["concept_image"] = {
        "revision_id": "revision-first",
        "mode": "generated",
        "image_prompt": "first",
        "image_data_url": "data:image/jpeg;base64,Zmlyc3Q=",
        "generated_at": first["generated_at"],
        "source": "uploaded_room_photo",
        "revision_text": "Initial generated design",
    }
    api_main.design_store.save(first["design_id"], first)

    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    second_session = create_session(client, {
        "brief": brief.model_dump(mode="json"),
        "user_id": "homeowner-anaya",
        "project_id": "project-bedroom",
        "project_name": "Bedroom",
    })
    second = client.post("/api/chat", json={"session_id": second_session["session_id"], "message": "Second version"}).json()["design"]
    second["concept_image"] = {
        "revision_id": "revision-second",
        "mode": "generated",
        "image_prompt": "second",
        "image_data_url": "data:image/jpeg;base64,c2Vjb25k",
        "generated_at": second["generated_at"],
        "source": "text_prompt",
        "revision_text": "Initial generated design",
    }
    api_main.design_store.save(second["design_id"], second)

    loaded = client.get(f"/api/design/{second['design_id']}").json()["design"]

    assert loaded["source_images"] == ["data:image/jpeg;base64,c291cmNl"]
    assert [entry["revision_id"] for entry in loaded["concept_history"]] == ["revision-first", "revision-second"]
    assert [entry["label"] for entry in loaded["concept_history"]] == ["Original design", "Version 2"]
    assert loaded["concept_history"][1]["revision_text"] == "Regenerated design"
    assert all(entry["selected_products"] for entry in loaded["concept_history"])


def test_concept_image_returns_prompt_without_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/concept-image",
        json={
            "project_type": "renovation",
            "room_type": "living_room",
            "dimensions": "10 x 12 ft",
            "style_words": ["warm", "modern"],
            "constraints": ["kid-friendly"],
            "questionnaire": {"mood": "calm", "priority": "storage"},
            "photo_notes": ["room.jpg: existing sofa and north window"],
            "vastu_enabled": True,
            "grounded_design": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "prompt_only"
    assert payload["image_data_url"] is None
    assert "renovation" in payload["image_prompt"]
    assert "Vastu-aware placement" in payload["image_prompt"]
    assert_no_secret_exposure(payload)


def test_concept_image_network_failure_is_recoverable(monkeypatch) -> None:
    class OfflineAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, **kwargs):
            request = api_main.httpx.Request("POST", url)
            raise api_main.httpx.ConnectError("offline", request=request)

    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.setattr(api_main.httpx, "AsyncClient", OfflineAsyncClient)
    client = TestClient(app)

    response = client.post(
        "/api/concept-image",
        json={
            "project_type": "new_space",
            "room_type": "study",
            "dimensions": "10 x 12 ft",
            "style_words": ["minimal"],
            "vastu_enabled": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "prompt_only"
    assert payload["image_data_url"] is None
    assert "design request was saved" in payload["notes"][0]


def test_concept_image_prompt_is_saved_to_the_design_without_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API", raising=False)
    client = TestClient(app)
    brief = create_room_brief(room_type="living_room", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "user_id": "homeowner-anaya", "project_id": "project-living"})
    chat_response = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create design"})
    assert chat_response.status_code == 200
    design_id = chat_response.json()["design"]["design_id"]

    concept_response = client.post(
        "/api/concept-image",
        json={
            "design_id": design_id,
            "project_type": "new_space",
            "room_type": "living_room",
            "dimensions": "12 x 14 ft",
            "style_words": ["warm"],
            "constraints": ["storage"],
            "questionnaire": {"priority": "storage"},
            "photo_notes": [],
            "vastu_enabled": False,
            "grounded_design": chat_response.json()["design"],
        },
    )

    assert concept_response.status_code == 200
    fetched = client.get(f"/api/design/{design_id}").json()["design"]
    assert fetched["concept_image"]["mode"] == "prompt_only"
    assert fetched["concept_image"]["image_data_url"] is None
    assert "living room" in fetched["concept_image"]["image_prompt"]


def test_concept_image_calls_openai_and_saves_generated_image(monkeypatch) -> None:
    class FakeImageResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": [{"b64_json": "abc123"}]}

    class FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, **kwargs) -> FakeImageResponse:
            calls.append({"url": url, "headers": headers, **kwargs})
            return FakeImageResponse()

    calls: list[dict] = []
    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.setattr(api_main.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(app)
    brief = create_room_brief(room_type="living_room", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "user_id": "homeowner-anaya", "project_id": "project-living"})
    chat_response = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create design"})
    design_id = chat_response.json()["design"]["design_id"]

    concept_response = client.post(
        "/api/concept-image",
        json={
            "design_id": design_id,
            "project_type": "new_space",
            "room_type": "living_room",
            "dimensions": "12 x 14 ft",
            "style_words": ["warm"],
            "constraints": [],
            "questionnaire": {},
            "photo_notes": [],
            "vastu_enabled": False,
            "grounded_design": chat_response.json()["design"],
        },
    )

    assert concept_response.status_code == 200
    payload = concept_response.json()
    assert payload["mode"] == "generated"
    assert payload["image_data_url"] == "data:image/jpeg;base64,abc123"
    assert payload["revision_id"].startswith("revision-")
    assert len(payload["concept_history"]) == 1
    assert payload["concept_history"][0]["selected_products"]
    assert calls[0]["url"] == "https://api.openai.com/v1/images/edits"
    assert calls[0]["data"]["model"] == "gpt-image-2"
    assert calls[0]["files"]
    assert len(calls[0]["files"]) == len(chat_response.json()["design"]["grounder_output"]["grounded_slots"])
    assert "exact" in calls[0]["files"][0][1][0]
    fetched = client.get(f"/api/design/{design_id}").json()["design"]
    assert fetched["concept_image"]["image_data_url"] == "data:image/jpeg;base64,abc123"
    assert_no_secret_exposure(payload)


def test_concept_image_edits_uploaded_room_photo(monkeypatch) -> None:
    class FakeImageResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": [{"b64_json": "edited456"}]}

    class FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, **kwargs) -> FakeImageResponse:
            calls.append({"url": url, "headers": headers, **kwargs})
            return FakeImageResponse()

    calls: list[dict] = []
    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.setattr(api_main.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(app)

    concept_response = client.post(
        "/api/concept-image",
        json={
            "project_type": "renovation",
            "room_type": "living_room",
            "dimensions": "12 x 14 ft",
            "style_words": ["warm", "modern"],
            "constraints": ["storage"],
            "questionnaire": {"priority": "storage"},
            "photo_notes": ["uploaded-room.jpg: existing room"],
            "photo_data_urls": ["data:image/jpeg;base64,aGVsbG8="],
            "vastu_enabled": True,
            "grounded_design": None,
        },
    )

    assert concept_response.status_code == 200
    payload = concept_response.json()
    assert payload["mode"] == "generated"
    assert payload["image_data_url"] == "data:image/jpeg;base64,edited456"
    assert calls[0]["url"] == "https://api.openai.com/v1/images/edits"
    assert calls[0]["data"]["model"] == "gpt-image-2"
    assert "Preserve the user's actual room geometry" in calls[0]["data"]["prompt"]
    assert calls[0]["files"][0][0] == "image[]"
    assert calls[0]["files"][0][1][0].startswith("1-original-room-photo-")
    assert calls[0]["files"][0][1][1] == b"hello"
    assert calls[0]["files"][0][1][2] == "image/jpeg"
    assert_no_secret_exposure(payload)


def test_revision_reuses_saved_room_and_current_design_without_replanning(monkeypatch) -> None:
    class FakeImageResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": [{"b64_json": "cmV2aXNlZA=="}]}

    class FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, **kwargs) -> FakeImageResponse:
            calls.append({"url": url, "headers": headers, **kwargs})
            return FakeImageResponse()

    calls: list[dict] = []
    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.setattr(api_main.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(app)
    brief = create_room_brief(room_type="living_room", width=12, depth=14, units="ft", budget_inr=180000)
    api_main.planner_client_override = FakePlannerClient(planner_payload(brief))
    session = create_session(client, {"brief": brief.model_dump(mode="json"), "user_id": "homeowner-anaya"})
    created = client.post("/api/chat", json={"session_id": session["session_id"], "message": "Create design"}).json()["design"]
    original_item_ids = [slot["selected_item"]["item_id"] for slot in created["grounder_output"]["grounded_slots"]]
    created["source_images"] = ["data:image/jpeg;base64,aGVsbG8="]
    created["concept_image"] = {
        "mode": "generated",
        "image_prompt": "first version",
        "image_data_url": "data:image/jpeg;base64,d29ybGQ=",
        "generated_at": created["generated_at"],
        "source": "uploaded_room_photo",
    }
    api_main.design_store.save(created["design_id"], created)
    loaded = client.get(f"/api/design/{created['design_id']}").json()["design"]
    base_revision_id = loaded["concept_history"][0]["revision_id"]

    revised_response = client.post(
        f"/api/design/{created['design_id']}/revise",
        json={"message": "Make the curtains olive and change nothing else."},
    )
    assert revised_response.status_code == 200
    revised = revised_response.json()["design"]
    revised_item_ids = [slot["selected_item"]["item_id"] for slot in revised["grounder_output"]["grounded_slots"]]
    assert revised_item_ids == original_item_ids
    assert revised["last_revision_request"] == "Make the curtains olive and change nothing else."

    concept_response = client.post(
        "/api/concept-image",
        json={
            "design_id": created["design_id"],
            "project_type": "renovation",
            "room_type": "living_room",
            "dimensions": "12 x 14 ft",
            "style_words": ["modern"],
            "base_revision_id": base_revision_id,
            "revision_mode": "variation",
            "questionnaire": {
                "colour_palette": "Modern: Porcelain #E9E5DC, Walnut #76523B, Olive #6F765A, Charcoal #333734, Burnt Rust #B85C3E",
                "colour_distribution": "Show at least four palette colours.",
            },
            "grounded_design": revised,
        },
    )

    assert concept_response.status_code == 200
    assert calls[0]["url"] == "https://api.openai.com/v1/images/edits"
    assert calls[0]["files"][0][1][1] == b"world"
    assert calls[0]["files"][1][1][1] == b"hello"
    assert len(calls[0]["files"]) == 2
    assert "input_fidelity" not in calls[0]["data"]
    assert "Make the curtains olive and change nothing else" in calls[0]["data"]["prompt"]
    assert "Create a visibly different design alternative" in calls[0]["data"]["prompt"]
    assert "Show at least four palette colours" in calls[0]["data"]["prompt"]
    fetched = client.get(f"/api/design/{created['design_id']}").json()["design"]
    assert fetched["source_images"] == ["data:image/jpeg;base64,aGVsbG8="]
    assert fetched["concept_image"]["source"] == "revision_from_original_and_current"
    assert len(fetched["concept_history"]) == 2
    assert fetched["concept_history"][0]["image_data_url"] == "data:image/jpeg;base64,d29ybGQ="
    assert fetched["concept_history"][1]["revision_text"] == "Make the curtains olive and change nothing else."
    assert fetched["concept_history"][1]["base_revision_id"] == base_revision_id
    assert fetched["concept_history"][1]["selected_products"]

    original_export = client.get(
        f"/api/export/{created['design_id']}",
        params={"revision_id": base_revision_id},
    )
    assert original_export.status_code == 200
    assert original_export.json()["revision_id"] == base_revision_id
    assert original_export.json()["revision_label"] == "Original design"
    assert original_export.json()["concept_image_data_url"] == "data:image/jpeg;base64,d29ybGQ="
    assert [item["item_id"] for item in original_export.json()["selected_items"]] == original_item_ids

    revised_revision_id = fetched["concept_history"][1]["revision_id"]
    revised_export = client.get(
        f"/api/export/{created['design_id']}",
        params={"revision_id": revised_revision_id},
    )
    assert revised_export.status_code == 200
    assert revised_export.json()["revision_id"] == revised_revision_id
    assert revised_export.json()["revision_label"] == "Version 2"
    assert revised_export.json()["concept_image_data_url"] == "data:image/jpeg;base64,cmV2aXNlZA=="
    assert client.get(
        f"/api/export/{created['design_id']}",
        params={"revision_id": "revision-not-in-project"},
    ).status_code == 422


def test_chat_returns_missing_api_key_error_without_backend_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API", raising=False)
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
