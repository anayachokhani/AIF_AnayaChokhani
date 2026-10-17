"""Server-side Marble image-to-world integration and persistent generation jobs."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import math
import os
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

API_BASE = "https://api.worldlabs.ai/marble/v1"
WORLD_PROMPT = (
    "Convert this interior design image into an explorable 3D world. "
    "Preserve the room layout, architectural proportions, furniture positions, "
    "materials, colours, decor and lighting shown in the image. Reconstruct a "
    "coherent interior that the viewer can move through and look around, with "
    "plausible depth and consistent unseen areas. Keep the design faithful to the reference."
)
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class WorldRequest(BaseModel):
    image_data_url: str = Field(min_length=1, max_length=17_000_000)
    display_name: str = Field(default="Interior design world", min_length=1, max_length=64)


def fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def image_base64(data_url: str) -> str:
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)", data_url)
    if not match:
        raise fail(422, "invalid_image", "A PNG, JPEG or WebP image data URL is required.")
    encoded = re.sub(r"\s", "", match[2])
    try:
        decoded = base64.b64decode(encoded, validate=True)
        if len(decoded) > MAX_IMAGE_BYTES:
            raise fail(413, "image_too_large", "The design image must be under 12 MB.")
        with Image.open(io.BytesIO(decoded)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Unsupported image format")
            image.verify()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise fail(422, "invalid_image", "The design image could not be decoded.") from exc
    return encoded


async def marble_request(method: str, path: str, payload: dict | None = None) -> dict:
    key = os.environ.get("WORLDLABS_MARBLE_API_KEY", "").strip()
    if not key:
        raise fail(503, "missing_marble_api_key", "Set WORLDLABS_MARBLE_API_KEY on the backend to create 3D worlds.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            response = await client.request(
                method, f"{API_BASE}/{path}", json=payload,
                headers={"WLT-Api-Key": key, "Content-Type": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise fail(504, "marble_timeout", "Marble did not respond in time. Check the saved job before trying again.") from exc
    except httpx.RequestError as exc:
        raise fail(502, "marble_unavailable", "Could not connect to Marble. Please check again shortly.") from exc
    if response.is_error:
        messages = {
            401: "The backend Marble API key was rejected.",
            403: "The Marble API key does not have access to this world.",
            402: "The Marble account needs API credits to generate this world.",
            429: "Marble is busy. Please check again shortly.",
            400: "Marble could not accept this image or prompt.",
            422: "Marble could not accept this image or prompt.",
        }
        # Never forward provider bodies, which can echo request data or secrets.
        status = response.status_code if response.status_code in {402, 429} else 502
        raise fail(status, "marble_request_failed", messages.get(response.status_code, "Marble could not complete the request. Please check again shortly."))
    try:
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result
    except ValueError as exc:
        raise fail(502, "marble_invalid_response", "Marble returned an unexpected response.") from exc


def https_url(value: Any) -> str | None:
    if isinstance(value, str) and urlparse(value).scheme == "https" and urlparse(value).hostname:
        return value
    return None


def world_assets(world: dict) -> dict:
    assets = world.get("assets") or {}
    splats = assets.get("splats") or {}
    urls = splats.get("spz_urls") or {}
    semantics = splats.get("semantics_metadata") or {}
    scale = semantics.get("metric_scale_factor", 1)
    offset = semantics.get("ground_plane_offset", 0)
    scale = scale if isinstance(scale, (int, float)) and math.isfinite(scale) and scale > 0 else 1
    offset = offset if isinstance(offset, (int, float)) and math.isfinite(offset) else 0
    return {
        "world_id": world.get("world_id"),
        "world_url": https_url(world.get("world_marble_url")),
        "splat_url": next((https_url(urls.get(size)) for size in ("500k", "100k", "full_res") if https_url(urls.get(size))), None),
        "metric_scale_factor": scale,
        "ground_plane_offset": offset,
    }


def create_marble_router(
    owned_design: Callable[[str, Request], dict],
    save_design: Callable[[str, dict], None],
) -> APIRouter:
    router = APIRouter(prefix="/api/design/{design_id}/worlds", tags=["Marble worlds"])
    submission_lock = asyncio.Lock()

    def persist(design_id: str, request: Request, image_hash: str, job: dict) -> None:
        # Re-read after network awaits so a revision made meanwhile is not overwritten.
        design = owned_design(design_id, request)
        design.setdefault("marble_worlds", {})[image_hash] = job
        save_design(design_id, design)

    async def update_job(job: dict) -> dict:
        job = dict(job)
        if job["status"] == "failed":
            return job
        if job.get("world_id"):
            world = await marble_request("GET", f"worlds/{quote(job['world_id'], safe='')}")
            return {**job, **world_assets(world), "status": "ready"}
        operation = await marble_request("GET", f"operations/{quote(job['operation_id'], safe='')}")
        if operation.get("error"):
            return {**job, "status": "failed", "message": "Marble could not generate this world. You can retry with this image."}
        if not operation.get("done"):
            return job
        result = operation.get("response") or {}
        if not isinstance(result, dict) or not result.get("world_id"):
            raise fail(502, "marble_invalid_response", "Marble completed without a world ID. Check again shortly.")
        world = await marble_request("GET", f"worlds/{quote(result['world_id'], safe='')}")
        return {**job, **world_assets(world), "status": "ready"}

    @router.post("")
    async def generate(design_id: str, payload: WorldRequest, request: Request) -> dict:
        async with submission_lock:
            design = owned_design(design_id, request)
            images = [design.get("concept_image") or {}, *design.get("concept_history", [])]
            if not any(entry.get("image_data_url") == payload.image_data_url for entry in images):
                raise fail(422, "invalid_design_image", "Choose a generated image saved with this design.")
            image_hash = hashlib.sha256(payload.image_data_url.encode()).hexdigest()
            existing = design.get("marble_worlds", {}).get(image_hash)
            if existing and existing.get("status") != "failed":
                return existing
            encoded = image_base64(payload.image_data_url)
            operation = await marble_request("POST", "worlds:generate", {
                "display_name": payload.display_name,
                "permission": {"public": False},
                "world_prompt": {
                    "type": "image", "text_prompt": WORLD_PROMPT,
                    "image_prompt": {"source": "data_base64", "data_base64": encoded},
                },
            })
            if not isinstance(operation.get("operation_id"), str) or not operation["operation_id"]:
                raise fail(502, "marble_invalid_response", "Marble did not return a generation job ID.")
            job = {"image_hash": image_hash, "operation_id": operation["operation_id"], "status": "generating"}
            if operation.get("error"):
                job.update(status="failed", message="Marble could not generate this world. You can retry.")
            persist(design_id, request, image_hash, job)
            return job

    @router.get("/{image_hash}")
    async def status(design_id: str, image_hash: str, request: Request) -> dict:
        design = owned_design(design_id, request)
        if not re.fullmatch(r"[a-f0-9]{64}", image_hash):
            raise fail(422, "invalid_image_hash", "Invalid design image identifier.")
        job = design.get("marble_worlds", {}).get(image_hash)
        if not job:
            return {"status": "not_started", "image_hash": image_hash}
        job = await update_job(job)
        persist(design_id, request, image_hash, job)
        return job

    return router
