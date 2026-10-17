import asyncio
import base64
from copy import deepcopy
import hashlib
import io
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from formaos.api import marble


def make_image(colour="red"):
    data = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(data, "PNG")
    return "data:image/png;base64," + base64.b64encode(data.getvalue()).decode()


@pytest.fixture
def setup_api(monkeypatch):
    image = make_image()
    design = {"concept_image": {"image_data_url": image}, "concept_history": []}
    store = {"room": design}
    app = FastAPI()

    def owned(design_id, request):
        if request.headers.get("X-Test-Owner") == "other":
            raise HTTPException(404, "design not found")
        if design_id not in store:
            raise HTTPException(404, "design not found")
        return deepcopy(store[design_id])

    app.include_router(marble.create_marble_router(owned, lambda key, value: store.update({key: value})))
    remote = AsyncMock()
    monkeypatch.setattr(marble, "marble_request", remote)
    with TestClient(app) as client:
        yield client, store, image, remote


def test_submit_resume_complete_and_refresh_assets_without_duplicate_generation(setup_api):
    client, store, image, remote = setup_api
    remote.return_value = {"operation_id": "op-1", "done": False}
    result = client.post("/api/design/room/worlds", json={"image_data_url": image})
    assert result.status_code == 200
    job = result.json()
    assert job["status"] == "generating"
    assert job["image_hash"] == hashlib.sha256(image.encode()).hexdigest()
    payload = remote.call_args.args[2]
    assert payload["world_prompt"]["image_prompt"] == {"source": "data_base64", "data_base64": image.split(",")[1]}
    assert "explorable 3D world" in payload["world_prompt"]["text_prompt"]
    assert payload["permission"] == {"public": False}
    assert store["room"]["marble_worlds"][job["image_hash"]] == job

    assert client.post("/api/design/room/worlds", json={"image_data_url": image}).json() == job
    assert remote.await_count == 1
    remote.return_value = {"operation_id": "op-1", "done": False}
    path = f"/api/design/room/worlds/{job['image_hash']}"
    assert client.get(path).json()["status"] == "generating"

    world = {"world_id": "world-1", "world_marble_url": "https://marble.worldlabs.ai/world/world-1",
             "assets": {"splats": {"spz_urls": {"500k": "https://assets.worldlabs.ai/room.spz"},
                                    "semantics_metadata": {"metric_scale_factor": 1.2, "ground_plane_offset": 0.3}}}}
    remote.side_effect = [{"done": True, "response": {"world_id": "world-1"}}, world]
    finished = client.get(path).json()
    assert finished["status"] == "ready"
    assert finished["splat_url"] == "https://assets.worldlabs.ai/room.spz"
    assert finished["metric_scale_factor"] == 1.2
    remote.side_effect = None
    remote.return_value = world
    assert client.get(path).json()["world_id"] == "world-1"
    assert remote.call_args.args == ("GET", "worlds/world-1")


def test_revisions_have_distinct_worlds_and_unknown_images_are_rejected(setup_api):
    client, store, image, remote = setup_api
    unknown = make_image("blue")
    assert client.post("/api/design/room/worlds", json={"image_data_url": unknown}).status_code == 422
    remote.assert_not_awaited()
    store["room"]["concept_history"] = [{"image_data_url": unknown}]
    remote.side_effect = [{"operation_id": "op-old"}, {"operation_id": "op-new"}]
    first = client.post("/api/design/room/worlds", json={"image_data_url": image}).json()
    second = client.post("/api/design/room/worlds", json={"image_data_url": unknown}).json()
    assert first["image_hash"] != second["image_hash"]
    assert len(store["room"]["marble_worlds"]) == 2


def test_ownership_applies_to_submission_and_polling(setup_api):
    client, _, image, remote = setup_api
    headers = {"X-Test-Owner": "other"}
    assert client.post("/api/design/room/worlds", json={"image_data_url": image}, headers=headers).status_code == 404
    assert client.get("/api/design/room/worlds/" + "a" * 64, headers=headers).status_code == 404
    remote.assert_not_awaited()


def test_failed_job_can_be_retried_and_provider_error_is_not_exposed(setup_api):
    client, _, image, remote = setup_api
    remote.return_value = {"operation_id": "op-fail"}
    job = client.post("/api/design/room/worlds", json={"image_data_url": image}).json()
    remote.return_value = {"done": True, "error": {"message": "secret-request-data"}}
    response = client.get(f"/api/design/room/worlds/{job['image_hash']}")
    assert response.json()["status"] == "failed"
    assert "secret-request-data" not in response.text
    remote.return_value = {"operation_id": "op-retry"}
    assert client.post("/api/design/room/worlds", json={"image_data_url": image}).json()["operation_id"] == "op-retry"


def test_pending_job_survives_transient_poll_failure(setup_api):
    client, store, image, remote = setup_api
    remote.return_value = {"operation_id": "op-1"}
    job = client.post("/api/design/room/worlds", json={"image_data_url": image}).json()
    remote.side_effect = marble.fail(504, "marble_timeout", "Check again")
    assert client.get(f"/api/design/room/worlds/{job['image_hash']}").status_code == 504
    assert store["room"]["marble_worlds"][job["image_hash"]]["status"] == "generating"


def test_status_for_unstarted_image_does_not_call_provider(setup_api):
    client, _, _, remote = setup_api
    assert client.get("/api/design/room/worlds/" + "a" * 64).json()["status"] == "not_started"
    remote.assert_not_awaited()


def test_corrupt_saved_image_is_rejected_before_submission(setup_api):
    client, store, _, remote = setup_api
    image = "data:image/png;base64,YmFk"
    store["room"]["concept_image"]["image_data_url"] = image
    assert client.post("/api/design/room/worlds", json={"image_data_url": image}).status_code == 422
    remote.assert_not_awaited()


def test_missing_key_is_a_clear_configuration_error(monkeypatch):
    monkeypatch.delenv("WORLDLABS_MARBLE_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(marble.marble_request("POST", "worlds:generate", {}))
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "missing_marble_api_key"


@pytest.mark.parametrize("status,expected", [(401, 502), (402, 402), (429, 429), (500, 502)])
def test_provider_failures_are_sanitized(monkeypatch, status, expected):
    monkeypatch.setenv("WORLDLABS_MARBLE_API_KEY", "private-marble-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"detail": "private-marble-key"}))
    original = httpx.AsyncClient
    monkeypatch.setattr(marble.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as error:
        asyncio.run(marble.marble_request("POST", "worlds:generate", {}))
    assert error.value.status_code == expected
    assert "private-marble-key" not in str(error.value.detail)


def test_main_application_mounts_marble_routes_with_account_auth(monkeypatch):
    from formaos.api import main
    monkeypatch.setenv("FORMAOS_REQUIRE_AUTH", "1")
    with TestClient(main.app) as client:
        response = client.get("/api/design/missing/worlds/" + "a" * 64)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
