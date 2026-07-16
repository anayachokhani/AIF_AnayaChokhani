from __future__ import annotations

import asyncio
import base64
import binascii
from copy import deepcopy
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
from datetime import UTC, datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from formaos.agents.graph_loop import AgentLoopResult, run_agent_loop
from formaos.agents.critic import critique_design
from formaos.agents.grounder import ground_design
from formaos.agents.planner import PlannerClient
from formaos.catalogue.index_catalogue import search_items
from formaos.contracts import RoomBrief
from formaos.room_state import (
    InMemoryStateStore,
    brief_dimensions_cm,
    create_room_brief,
    parse_room_brief_text,
    to_graph_state,
)
from formaos.vastu.schema import load_rule_set

load_dotenv()

APP_ROOT = Path(__file__).resolve().parents[3]
CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")
CHROMA_PATH = Path("data/vectorstores/chroma")
RUNTIME_DATA_DIR = Path(os.environ.get("FORMAOS_DATA_DIR", APP_ROOT / ".formaos-data")).expanduser()
LEGACY_DESIGN_STORE_PATH = Path("/tmp/formaos-app/saved_designs/designs.json")
LEGACY_AUTH_STORE_PATH = Path("/tmp/formaos-app/auth/accounts.json")


def persistent_store_path(environment_name: str, relative_path: str, legacy_path: Path) -> Path:
    configured = os.environ.get(environment_name)
    destination = Path(configured).expanduser() if configured else RUNTIME_DATA_DIR / relative_path
    if not configured and not destination.exists() and legacy_path.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, destination)
    return destination


DESIGN_STORE_PATH = persistent_store_path("FORMAOS_DESIGN_STORE_PATH", "saved_designs/designs.json", LEGACY_DESIGN_STORE_PATH)
AUTH_STORE_PATH = persistent_store_path("FORMAOS_AUTH_STORE_PATH", "auth/accounts.json", LEGACY_AUTH_STORE_PATH)
if AUTH_STORE_PATH.exists():
    AUTH_STORE_PATH.parent.chmod(0o700)
    AUTH_STORE_PATH.chmod(0o600)
AUTH_COOKIE_NAME = "formaos_session"
AUTH_SESSION_DAYS = 30

app = FastAPI(title="FormaOS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_store = InMemoryStateStore()
planner_client_override: PlannerClient | None = None
session_users: dict[str, str] = {}
session_projects: dict[str, dict[str, str]] = {}


def atomic_json_write(path: Path, payload: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if private:
            path.chmod(0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


class FileDesignStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._designs: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._designs = {}
            return
        if isinstance(payload, dict):
            self._designs = {str(key): value for key, value in payload.items() if isinstance(value, dict)}

    def _flush(self) -> None:
        atomic_json_write(self.path, self._designs)

    def get(self, design_id: str) -> dict[str, Any] | None:
        self._load()
        return self._designs.get(design_id)

    def save(self, design_id: str, design: dict[str, Any]) -> None:
        self._load()
        self._designs[design_id] = design
        self._flush()

    def clear(self) -> None:
        self._designs = {}
        self._loaded = True
        if self.path.exists():
            self.path.unlink()

    def delete_project(self, project_id: str, user_id: str) -> list[dict[str, Any]]:
        self._load()
        deleted = [
            design
            for design in self._designs.values()
            if str(design.get("project_id") or design.get("session_id")) == project_id
            and design.get("user_id") == user_id
        ]
        if not deleted:
            return []
        deleted_ids = {str(design.get("design_id")) for design in deleted}
        self._designs = {
            design_id: design
            for design_id, design in self._designs.items()
            if design_id not in deleted_ids
        }
        self._flush()
        return deleted

    def values(self) -> list[dict[str, Any]]:
        self._load()
        return list(self._designs.values())


design_store = FileDesignStore(DESIGN_STORE_PATH)


class FileAuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._users: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._users = payload.get("users", {}) if isinstance(payload.get("users"), dict) else {}
        self._sessions = payload.get("sessions", {}) if isinstance(payload.get("sessions"), dict) else {}

    def _flush(self) -> None:
        atomic_json_write(self.path, {"users": self._users, "sessions": self._sessions}, private=True)

    @staticmethod
    def _password_hash(password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 210_000)
        return digest.hex()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_user(self, name: str, email: str, password: str) -> dict[str, str]:
        self._load()
        normalized_email = email.strip().lower()
        if any(user.get("email") == normalized_email for user in self._users.values()):
            raise typed_error(409, "account_exists", "an account already exists for this email")
        salt = secrets.token_hex(16)
        user_id = f"homeowner-{uuid4().hex[:16]}"
        user = {
            "id": user_id,
            "name": name.strip(),
            "email": normalized_email,
            "location": "",
            "home_type": "apartment",
            "preferred_units": "ft",
            "password_salt": salt,
            "password_hash": self._password_hash(password, salt),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._users[user_id] = user
        self._flush()
        return self.public_user(user)

    def update_profile(
        self,
        user_id: str,
        *,
        name: str,
        location: str,
        home_type: str,
        preferred_units: str,
    ) -> dict[str, str]:
        self._load()
        user = self._users.get(user_id)
        if user is None:
            raise typed_error(404, "not_found", "account not found")
        user.update(
            {
                "name": name.strip(),
                "location": location.strip(),
                "home_type": home_type,
                "preferred_units": preferred_units,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        self._flush()
        return self.public_user(user)

    def authenticate(self, email: str, password: str) -> dict[str, str] | None:
        self._load()
        normalized_email = email.strip().lower()
        user = next((candidate for candidate in self._users.values() if candidate.get("email") == normalized_email), None)
        if not user:
            return None
        candidate_hash = self._password_hash(password, str(user["password_salt"]))
        if not hmac.compare_digest(candidate_hash, str(user["password_hash"])):
            return None
        return self.public_user(user)

    def create_session(self, user_id: str) -> str:
        self._load()
        token = secrets.token_urlsafe(32)
        self._sessions[self._token_hash(token)] = {
            "user_id": user_id,
            "expires_at": (datetime.now(UTC) + timedelta(days=AUTH_SESSION_DAYS)).isoformat(),
        }
        self._flush()
        return token

    def user_for_token(self, token: str | None) -> dict[str, str] | None:
        self._load()
        if not token:
            return None
        token_hash = self._token_hash(token)
        session = self._sessions.get(token_hash)
        if not session:
            return None
        try:
            expired = datetime.fromisoformat(str(session["expires_at"])) <= datetime.now(UTC)
        except (KeyError, ValueError):
            expired = True
        if expired:
            self._sessions.pop(token_hash, None)
            self._flush()
            return None
        user = self._users.get(str(session.get("user_id")))
        return self.public_user(user) if user else None

    def revoke(self, token: str | None) -> None:
        self._load()
        if token and self._sessions.pop(self._token_hash(token), None) is not None:
            self._flush()

    def clear(self) -> None:
        self._users = {}
        self._sessions = {}
        self._loaded = True
        if self.path.exists():
            self.path.unlink()

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(user["id"]),
            "name": str(user["name"]),
            "email": str(user["email"]),
            "location": str(user.get("location") or ""),
            "home_type": str(user.get("home_type") or "apartment"),
            "preferred_units": str(user.get("preferred_units") or "ft"),
        }


auth_store = FileAuthStore(AUTH_STORE_PATH)

DEMO_ROOM_CATEGORIES: dict[str, list[str]] = {
    "living_room": ["sofa", "chair", "table", "rug", "storage", "cabinet", "lamp", "mirror", "planter"],
    "bedroom": ["bed", "storage", "table", "cabinet", "rug", "lamp", "chair", "mirror", "planter"],
    "study": ["desk", "chair", "storage", "cabinet", "rug", "lamp", "table", "mirror", "planter"],
}

STYLE_PROFILES: dict[str, str] = {
    "modern": "Modern means clean lines, low-profile furniture, warm neutrals, walnut or teak, black metal accents, restrained abstract art, and uncluttered surfaces.",
    "minimal": "Minimal means negative space, pale oak, linen, hidden storage, very few objects, warm white walls, and quiet geometry.",
    "scandinavian": "Scandinavian means airy layouts, pale wood, wool, soft grey and oatmeal textiles, cozy lighting, simple storage, and practical warmth.",
    "boho": "Boho means layered rugs, jute, cane or rattan, terracotta, patterned cushions, indoor plants, handmade ceramics, and collected decor.",
    "contemporary": "Contemporary means curved furniture, sculptural lighting, abstract art, mixed stone wood and metal, muted rust or olive accents, and polished styling.",
    "classic": "Classic means symmetry, tailored upholstery, carved or turned wood, brass, framed artwork, graceful lamps, and warm cream or navy accents.",
    "japandi": "Japandi means low furniture, slatted wood, linen, clay, stone, natural oak, sparse styling, muted earthy neutrals, and calm asymmetry.",
    "industrial": "Industrial means cognac leather, black steel, reclaimed wood, brick or concrete texture, utilitarian lighting, and charcoal accents.",
}


class DemoPlannerClient:
    def __init__(self, brief: RoomBrief) -> None:
        self.brief = brief

    def complete(self, messages: list[dict[str, str]]) -> str:
        dims = brief_dimensions_cm(self.brief)
        categories = DEMO_ROOM_CATEGORIES.get(self.brief.room_type, DEMO_ROOM_CATEGORIES["living_room"])
        share = round(1 / len(categories), 4)
        return json.dumps(
            {
                "room_facts": {
                    "room_type": self.brief.room_type,
                    "width_cm": dims.width_cm,
                    "depth_cm": dims.depth_cm,
                    "budget_inr": self.brief.budget_inr,
                    "style_words": self.brief.style_words,
                },
                "constraints": self.brief.constraints,
                "needs_list": [
                    {
                        "category": category,
                        "purpose": f"{category} for the room",
                        "quantity": 1,
                        "priority": min(index + 1, 5),
                        "budget_share": share,
                        "style_tags": self.brief.style_words,
                        "constraints": self.brief.constraints,
                    }
                    for index, category in enumerate(categories)
                ],
                "missing_questions": [],
            }
        )


class SessionRequest(BaseModel):
    brief: RoomBrief | None = None
    message: str | None = Field(default=None, min_length=1)
    user_id: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    project_name: str | None = Field(default=None, min_length=1, max_length=160)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    max_retries: int = Field(default=2, ge=0, le=3)


class ReviseRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(default="Revise this design.", min_length=1)
    max_retries: int = Field(default=2, ge=0, le=3)
    refresh_products: bool = False


class SignUpRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=160, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=160)
    password: str = Field(..., min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    location: str = Field(default="", max_length=120)
    home_type: str = Field(default="apartment", pattern="^(apartment|house|condo|townhouse|other)$")
    preferred_units: str = Field(default="ft", pattern="^(ft|m|cm)$")


class SelectItemRequest(BaseModel):
    slot_id: str = Field(..., min_length=1, max_length=160)
    item_id: str = Field(..., min_length=1, max_length=160)


class ConceptImageRequest(BaseModel):
    design_id: str | None = Field(default=None, min_length=1, max_length=160)
    base_revision_id: str | None = Field(default=None, min_length=1, max_length=160)
    revision_mode: str = Field(default="targeted", pattern="^(targeted|variation)$")
    project_type: str = Field(..., pattern="^(renovation|new_space)$")
    room_type: str = Field(..., min_length=1)
    dimensions: str = ""
    style_words: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    questionnaire: dict[str, str] = Field(default_factory=dict)
    photo_notes: list[str] = Field(default_factory=list)
    photo_data_urls: list[str] = Field(default_factory=list, max_length=4)
    revision_text: str = Field(default="", max_length=1200)
    finish_schedule: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    vastu_enabled: bool = False
    grounded_design: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    errors: list[dict[str, Any]] | None = None
    error: str | None = None
    design: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str


class AuthUser(BaseModel):
    id: str
    name: str
    email: str
    location: str = ""
    home_type: str = "apartment"
    preferred_units: str = "ft"


class AuthResponse(BaseModel):
    user: AuthUser


class LogoutResponse(BaseModel):
    status: str


class DeleteProjectResponse(BaseModel):
    status: str
    deleted_designs: int


class SessionResponse(BaseModel):
    session_id: str
    state: dict[str, Any]


class ChatResponse(BaseModel):
    state: str
    design: dict[str, Any]


class DesignResponse(BaseModel):
    design: dict[str, Any]


class ConceptImageResponse(BaseModel):
    mode: str
    image_prompt: str
    image_data_url: str | None = None
    notes: list[str]
    revision_id: str | None = None
    concept_history: list[dict[str, Any]] = Field(default_factory=list)


class DesignSummary(BaseModel):
    design_id: str
    session_id: str
    project_id: str
    project_name: str
    user_id: str | None = None
    generated_at: str
    status: str
    room_type: str
    total_price_inr: int
    item_count: int
    style_words: list[str]
    preview_image_data_url: str | None = None
    preview_image_path: str | None = None


class DesignListResponse(BaseModel):
    designs: list[DesignSummary]
    count: int


class CatalogueSearchResponse(BaseModel):
    results: list[dict[str, Any]]
    count: int


class ExportResponse(BaseModel):
    design_id: str
    project_name: str
    generated_at: str
    revision_id: str | None = None
    concept_image_data_url: str | None = None
    source_image_data_url: str | None = None
    revision_label: str | None = None
    room_brief: dict[str, Any]
    user_requirements: dict[str, Any]
    selected_items: list[dict[str, Any]]
    finish_schedule: list[dict[str, Any]]
    total_price_inr: int
    budget_summary: dict[str, Any]
    fit_notes: list[str]
    vastu_summary: dict[str, Any]
    attribution: str


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_brief", "message": "request validation failed", "errors": exc.errors()}},
    )


def typed_error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def authenticated_user(request: Request, *, required: bool = True) -> dict[str, str] | None:
    user = auth_store.user_for_token(request.cookies.get(AUTH_COOKIE_NAME))
    if required and user is None:
        raise typed_error(401, "authentication_required", "sign in to continue")
    return user


def application_auth_required() -> bool:
    return os.environ.get("FORMAOS_REQUIRE_AUTH", "1") != "0"


def request_user(request: Request) -> dict[str, str] | None:
    return authenticated_user(request, required=application_auth_required())


def set_auth_cookie(response: Response, token: str) -> None:
    secure = os.environ.get("FORMAOS_COOKIE_SECURE") == "1"
    same_site = os.environ.get("FORMAOS_COOKIE_SAMESITE", "lax")
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
    )


def assert_design_owner(design: dict[str, Any], user: dict[str, str] | None) -> None:
    if user and design.get("user_id") != user["id"]:
        raise typed_error(404, "not_found", "design not found")


def assert_session_owner(session_id: str, user: dict[str, str] | None) -> None:
    owner_id = session_users.get(session_id)
    if user and owner_id and owner_id != user["id"]:
        raise typed_error(404, "not_found", "session not found")


def planner_client(brief: RoomBrief | None = None) -> PlannerClient | None:
    if planner_client_override is None and brief is not None and os.environ.get("FORMAOS_DEMO_PLANNER") == "1":
        return DemoPlannerClient(brief)
    return planner_client_override


def serializable_design(design_id: str, session_id: str, brief: RoomBrief, result: AgentLoopResult) -> dict[str, Any]:
    project = session_projects.get(session_id, {})
    state = state_store.get(session_id)
    return {
        "design_id": design_id,
        "session_id": session_id,
        "project_id": project.get("project_id") or session_id,
        "project_name": project.get("project_name") or brief.room_type.replace("_", " ").title(),
        "user_id": session_users.get(session_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "room_brief": brief.model_dump(mode="json"),
        "status": result.status,
        "planner_output": result.planner_output.model_dump(mode="json"),
        "designer_output": result.designer_output.model_dump(mode="json"),
        "grounder_output": result.grounder_output.model_dump(mode="json"),
        "critic_verdict": result.critic_verdict.model_dump(mode="json"),
        "chat_messages": list(state.messages) if state else [],
        "attempt_log": [entry.model_dump(mode="json") for entry in result.attempt_log],
        "retries_used": result.retries_used,
        "max_retries": result.max_retries,
    }


def summarize_design(design: dict[str, Any]) -> DesignSummary:
    room_facts = design.get("planner_output", {}).get("room_facts", {})
    grounded_slots = design.get("grounder_output", {}).get("grounded_slots", [])
    selected_count = sum(1 for slot in grounded_slots if slot.get("selected_item"))
    first_image_path = next(
        (
            (slot.get("selected_item") or {}).get("image_path")
            for slot in grounded_slots
            if (slot.get("selected_item") or {}).get("image_available")
            and (slot.get("selected_item") or {}).get("image_path")
        ),
        None,
    )
    concept_image = design.get("concept_image") or {}
    return DesignSummary(
        design_id=str(design["design_id"]),
        session_id=str(design["session_id"]),
        project_id=str(design.get("project_id") or design["session_id"]),
        project_name=str(design.get("project_name") or room_facts.get("room_type", "Room")).replace("_", " ").title(),
        user_id=design.get("user_id"),
        generated_at=str(design["generated_at"]),
        status=str(design["status"]),
        room_type=str(room_facts.get("room_type", "room")),
        total_price_inr=int(design.get("critic_verdict", {}).get("total_price_inr", 0)),
        item_count=selected_count,
        style_words=list(room_facts.get("style_words", [])),
        preview_image_data_url=concept_image.get("image_data_url"),
        preview_image_path=first_image_path,
    )


def clean_prompt_part(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def selected_item_lines(design: dict[str, Any] | None) -> list[str]:
    if not design:
        return []
    lines = []
    for slot in design.get("grounder_output", {}).get("grounded_slots", []):
        item = slot.get("selected_item")
        if not item:
            continue
        lines.append(
            clean_prompt_part(
                f"{slot.get('slot', {}).get('category', 'item')}: {item.get('title')} "
                f"({item.get('width_cm')} x {item.get('depth_cm')} cm), "
                f"material {item.get('material') or 'not specified'}, colour {item.get('color') or 'not specified'}, "
                f"zone {slot.get('placement_zone')}"
            )
        )
    return lines


def selected_product_snapshots(design: dict[str, Any] | None) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    if not design:
        return snapshots
    for grounded_slot in design.get("grounder_output", {}).get("grounded_slots", []):
        item = grounded_slot.get("selected_item") or {}
        if not item:
            continue
        snapshots.append(
            {
                **item,
                "category": grounded_slot.get("slot", {}).get("category", item.get("product_type", "item")),
                "placement_zone": grounded_slot.get("placement_zone"),
            }
        )
    return snapshots


def requested_product_categories(message: str, grounded_slots: list[dict[str, Any]]) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", message.lower()).strip()
    action_words = {"change", "replace", "swap", "refresh", "update", "make", "different", "new", "another"}
    if not action_words.intersection(normalized.split()):
        return set()
    categories = {
        str(slot.get("slot", {}).get("category") or "")
        for slot in grounded_slots
        if slot.get("slot", {}).get("category")
    }
    broad_terms = {"furniture", "furnishings", "products", "catalogue", "all", "every"}
    if broad_terms.intersection(normalized.split()):
        return categories
    return {
        category
        for category in categories
        if category.lower().replace("_", " ") in normalized
        or any(
            token in normalized.split()
            for token in category.lower().replace("_", " ").split()
            if len(token) > 2
        )
    }


def synchronize_refreshed_products(
    previous_slots: list[dict[str, Any]],
    refreshed_slots: list[dict[str, Any]],
    message: str,
) -> list[dict[str, Any]]:
    target_categories = requested_product_categories(message, previous_slots)
    if not target_categories:
        return refreshed_slots
    previous_by_slot = {
        str(slot.get("slot", {}).get("slot_id") or ""): slot
        for slot in previous_slots
    }
    meaningful_words = {
        word
        for word in re.sub(r"[^a-z0-9]+", " ", message.lower()).split()
        if len(word) > 2 and word not in {"change", "replace", "refresh", "update", "make", "different", "another", "furniture"}
    }
    for refreshed_slot in refreshed_slots:
        slot = refreshed_slot.get("slot", {})
        category = str(slot.get("category") or "")
        if category not in target_categories:
            previous = previous_by_slot.get(str(slot.get("slot_id") or ""))
            if previous:
                refreshed_slot["selected_item"] = previous.get("selected_item")
                refreshed_slot["alternatives"] = list(previous.get("alternatives") or [])
            continue
        previous = previous_by_slot.get(str(slot.get("slot_id") or ""), {})
        current_id = str((previous.get("selected_item") or {}).get("item_id") or "")
        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in [
            refreshed_slot.get("selected_item"),
            *(refreshed_slot.get("alternatives") or []),
            *(previous.get("alternatives") or []),
        ]:
            item_id = str((item or {}).get("item_id") or "")
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            candidates.append(dict(item))
        replacements = [item for item in candidates if str(item.get("item_id") or "") != current_id]
        if not replacements:
            continue

        def match_score(item: dict[str, Any]) -> tuple[int, int]:
            searchable = " ".join(
                str(item.get(field) or "").lower()
                for field in ("title", "color", "material", "style_text")
            )
            return sum(word in searchable for word in meaningful_words), -int(item.get("price_inr") or 0)

        selected = max(replacements, key=match_score)
        selected["placement_zone"] = refreshed_slot.get("placement_zone")
        refreshed_slot["selected_item"] = selected
        refreshed_slot["alternatives"] = [
            item for item in candidates if item.get("item_id") != selected.get("item_id")
        ][:3]
    return refreshed_slots


def project_product_index(design: dict[str, Any]) -> dict[str, dict[str, Any]]:
    project_id = str(design.get("project_id") or design.get("session_id"))
    owner_id = design.get("user_id")
    index: dict[str, dict[str, Any]] = {}
    for candidate in design_store.values():
        if str(candidate.get("project_id") or candidate.get("session_id")) != project_id:
            continue
        if candidate.get("user_id") != owner_id:
            continue
        for grounded_slot in candidate.get("grounder_output", {}).get("grounded_slots", []):
            slot = grounded_slot.get("slot", {})
            for item in [grounded_slot.get("selected_item"), *grounded_slot.get("alternatives", [])]:
                if not item or not item.get("item_id"):
                    continue
                index[str(item["item_id"])] = {
                    **item,
                    "category": slot.get("category", item.get("product_type", "item")),
                    "placement_zone": grounded_slot.get("placement_zone"),
                }
    return index


def concept_history_with_current(design: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not design:
        return []
    history = [dict(entry) for entry in design.get("concept_history", []) if entry.get("image_data_url")]
    current = design.get("concept_image") or {}
    current_image = current.get("image_data_url")
    if current_image and not any(entry.get("image_data_url") == current_image for entry in history):
        is_revision = str(current.get("source") or "").startswith("revision_")
        history.append(
            {
                **current,
                "revision_id": current.get("revision_id") or f"revision-{uuid4().hex[:12]}",
                "version": len(history) + 1,
                "label": "Saved design" if not history and is_revision else "Original design" if not history else f"Revision {len(history)}",
                "revision_text": current.get("revision_text") or "Previously generated design" if is_revision else "Initial generated design",
                "selected_products": selected_product_snapshots(design),
            }
        )
    return history


def project_concept_history(design: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    project_id = str(design.get("project_id") or design.get("session_id"))
    owner_id = design.get("user_id")
    project_designs = sorted(
        (
            candidate
            for candidate in design_store.values()
            if str(candidate.get("project_id") or candidate.get("session_id")) == project_id
            and candidate.get("user_id") == owner_id
        ),
        key=lambda candidate: str(candidate.get("generated_at") or ""),
    )
    merged: list[dict[str, Any]] = []
    seen_revisions: set[str] = set()
    seen_images: set[str] = set()
    recovered_sources: list[str] = []
    for candidate in project_designs:
        for source in candidate.get("source_images") or []:
            if source and source not in recovered_sources:
                recovered_sources.append(source)
        for entry in concept_history_with_current(candidate):
            revision_id = str(entry.get("revision_id") or "")
            image_data_url = str(entry.get("image_data_url") or "")
            if (revision_id and revision_id in seen_revisions) or (image_data_url and image_data_url in seen_images):
                continue
            copy = dict(entry)
            if not copy.get("selected_products"):
                copy["selected_products"] = selected_product_snapshots(candidate)
            if not copy.get("generated_at"):
                copy["generated_at"] = candidate.get("generated_at")
            merged.append(copy)
            if revision_id:
                seen_revisions.add(revision_id)
            if image_data_url:
                seen_images.add(image_data_url)
    merged.sort(key=lambda entry: str(entry.get("generated_at") or ""))
    for index, entry in enumerate(merged):
        entry["version"] = index + 1
        entry["label"] = "Original design" if index == 0 else f"Version {index + 1}"
        if index > 0 and entry.get("revision_text") == "Initial generated design":
            entry["revision_text"] = "Regenerated design"
    return merged, recovered_sources


def revision_visual_directive(revision_text: str) -> str:
    normalized = revision_text.lower()
    directives: list[str] = []
    if "calm" in normalized or "calmer" in normalized:
        directives.append(
            "Make calmness unmistakable: remove visual clutter, reduce small decor by about one third, use a softer low-contrast neutral palette, simplify artwork, and use diffused warm lighting."
        )
    if "warm" in normalized or "warmer" in normalized:
        directives.append(
            "Make warmth visible through warmer white balance, natural wood, warm-white lighting, and tactile beige or rust textiles."
        )
    if "bright" in normalized or "lighter" in normalized:
        directives.append(
            "Increase visible daylight, use lighter surfaces and window treatments, and lift dark shadows without changing the architecture."
        )
    if "minimal" in normalized:
        directives.append("Remove redundant objects and simplify silhouettes while retaining every approved functional furniture category.")
    return " ".join(directives) or "Apply the requested visual change at a clearly noticeable strength while keeping unrelated details fixed."


def style_profile_lines(style_words: list[str]) -> list[str]:
    lines: list[str] = []
    normalized_blob = " ".join(style_words).lower()
    for style, guidance in STYLE_PROFILES.items():
        if style in normalized_blob:
            lines.append(guidance)
    return lines


def vastu_prompt_directives(request: ConceptImageRequest) -> str:
    if not request.vastu_enabled:
        return "No Vastu overlay requested."

    grounded_slots = (request.grounded_design or {}).get("grounder_output", {}).get("grounded_slots", [])
    placement_lines = [
        f"place the {slot.get('slot', {}).get('category', 'item')} in the {slot.get('placement_zone')} zone"
        for slot in grounded_slots
        if slot.get("placement_zone")
    ]
    try:
        rules = load_rule_set(Path("data/vastu/vastu_rules_v1.json")).rules
    except (OSError, ValueError):
        rules = []
    categories = {str(slot.get("slot", {}).get("category", "")) for slot in grounded_slots}
    applicable = [
        rule
        for rule in rules
        if rule.room_type in {"any", request.room_type} and rule.object_class in categories
    ]
    orientation_lines = [
        f"orient the {rule.object_class} toward {' or '.join(rule.preferred_zones)}"
        for rule in applicable
        if rule.perspective == "orientation" and rule.preferred_zones
    ]
    colour_lines = [
        f"use {' or '.join(rule.preferred_colors)} cues for the {rule.object_class}"
        for rule in applicable
        if rule.preferred_colors
    ]
    directives = list(dict.fromkeys([*placement_lines, *orientation_lines, *colour_lines]))
    return (
        "Apply Vastu-aware placement as an active design constraint, not only a post-design score. "
        f"Follow these visible directives: {'; '.join(directives) or 'keep heavy objects south/west, natural elements north/east, and the center open'}. "
        "Do not move an approved item into a different compass zone."
    )


def build_concept_prompt(
    request: ConceptImageRequest,
    *,
    has_source_image: bool = False,
    has_previous_image: bool = False,
    reference_labels: list[str] | None = None,
) -> str:
    has_photo = any(request.photo_data_urls) or has_source_image
    project_label = "redesign of the uploaded existing room" if has_photo else (
        "renovation of an existing room" if request.project_type == "renovation" else "new interior design for an empty room"
    )
    answers = [f"{key}: {value}" for key, value in request.questionnaire.items() if value]
    colour_palette = request.questionnaire.get("colour_palette", "")
    colour_distribution = request.questionnaire.get("colour_distribution", "")
    item_lines = selected_item_lines(request.grounded_design)
    style_guidance = style_profile_lines(request.style_words)
    vastu = vastu_prompt_directives(request)
    if request.revision_text and request.revision_mode == "variation":
        revision_instruction = (
            f"Variation request: {clean_prompt_part(request.revision_text)}. Create a visibly different design alternative, not a copy of Image 1. "
            "Keep the same room shell, viewpoint, scale, furniture zones, and every exact approved catalogue product unless the grounded product list explicitly contains a replacement. Make at least five obvious coordinated changes across wall colour or treatment, curtains, lighting treatment, artwork, plants, textiles, and decorative objects without inventing replacement furniture. "
            "The result must be immediately distinguishable from Image 1 while still unmistakably depicting the same physical room."
        )
    elif request.revision_text:
        revision_instruction = (
            f"Revision request: {clean_prompt_part(request.revision_text)}. Change only what this request explicitly asks for. "
            "This is a constrained edit of Image 1, not a new room generation. The requested change must be clearly visible, but unrelated architecture and objects should remain as close to Image 1 as possible. "
            f"Implementation guidance: {revision_visual_directive(request.revision_text)} "
            "Do not return an unchanged copy of Image 1."
        )
    else:
        revision_instruction = "This is the first design pass; follow the approved room and product brief exactly."

    if has_previous_image and request.revision_mode == "variation":
        edit_boundary = (
            "Image 1 is the selected saved design and the primary variation reference. Preserve its exact camera position, lens perspective, crop, wall boundaries, doors, windows, ceiling, floor plane, and built-ins. "
            "Preserve the functional layout and major furniture zones, but deliberately restyle the movable design layer so the alternative is visibly new. Do not recompose, recrop, rotate, widen, mirror, or replace the room."
        )
    elif has_previous_image:
        edit_boundary = (
            "Image 1 is the selected saved design and the primary edit target. Preserve its exact pixel dimensions, camera position, lens perspective, crop, wall boundaries, doors, windows, ceiling, floor, built-ins, light direction, and furniture positions. "
            "Do not recompose, recrop, rotate, widen, mirror, restage, or replace the room."
        )
    else:
        edit_boundary = "Keep the same viewpoint and room envelope throughout this design."
    return "\n".join(
        part
        for part in [
            "Create a realistic interior design concept image for a homeowner.",
            f"Project: {project_label}.",
            f"Room: {request.room_type.replace('_', ' ')}. Dimensions: {request.dimensions or 'not specified'}.",
            f"Style direction: {', '.join(request.style_words) or 'warm, livable, practical'}.",
            f"Style interpretation rules: {' '.join(style_guidance) or 'Translate the selected style into distinct furniture shapes, materials, palette, art, lighting, and styling; do not make all styles look the same.'}",
            f"Required colour palette: {colour_palette or 'derive five distinct colours from the selected style'}. {colour_distribution or 'Use a dominant base, a natural material tone, a secondary hue, and two deliberate accents.'} Do not reduce the room to only beige and brown or reuse the same two-colour scheme for every style.",
            f"Constraints: {', '.join(request.constraints) or 'clear circulation, realistic furniture scale, comfortable use'}.",
            f"Designer questionnaire answers: {'; '.join(answers) or 'not provided'}.",
            f"Photo observations from uploaded room references: {'; '.join(request.photo_notes) or 'no photos uploaded yet; infer a neutral room shell'}.",
            f"Use these grounded product placements when visible: {'; '.join(item_lines) or 'use realistic furniture categories appropriate for the brief'}.",
            f"Image references are ordered as follows: {'; '.join(reference_labels or []) or 'none'}.",
            revision_instruction,
            vastu,
            "When an uploaded room image is provided, use it as the source image. Preserve the user's actual room geometry, camera angle, windows, doors, ceiling, floor plane, wall positions, and built-in architecture. Redesign the space by changing furniture, layout, palette, lighting, storage, textiles, and decor. Do not replace it with a different showroom or stock room.",
            edit_boundary,
            "Where product reference images are included, match their recognisable silhouette, upholstery or finish colour, material, and proportions. Do not substitute unrelated generic furniture.",
            "Render as a polished, photorealistic room concept. Keep architecture plausible, furniture scale accurate, circulation clear, and avoid text labels or watermarks.",
        ]
    )


def image_bytes_from_data_url(data_url: str) -> tuple[str, bytes]:
    match = re.match(r"^data:(image/(?:png|jpeg|jpg|webp));base64,(.+)$", data_url, re.DOTALL)
    if not match:
        raise typed_error(422, "invalid_image", "uploaded room photo must be a PNG, JPEG, or WEBP data URL")
    mime_type = "image/jpeg" if match.group(1) == "image/jpg" else match.group(1)
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise typed_error(422, "invalid_image", "uploaded room photo base64 data is invalid") from exc
    if len(image_bytes) > 12_000_000:
        raise typed_error(413, "image_too_large", "uploaded room photo must be under 12MB")
    return mime_type, image_bytes


class ImageServiceUnavailableError(RuntimeError):
    pass


async def generate_openai_image(prompt: str) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API")
    if not api_key:
        return None
    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")
    try:
        async with httpx.AsyncClient(timeout=140) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "prompt": prompt,
                    "size": "1536x1024",
                    "quality": os.environ.get("OPENAI_IMAGE_QUALITY", "medium"),
                    "output_format": "jpeg",
                },
            )
    except httpx.RequestError as exc:
        raise ImageServiceUnavailableError("OpenAI image generation could not be reached") from exc
    if response.status_code >= 400:
        raise typed_error(502, "image_generation_failed", "OpenAI image generation failed", error=response.text[:500])
    payload = response.json()
    image_base64 = payload.get("data", [{}])[0].get("b64_json")
    return f"data:image/jpeg;base64,{image_base64}" if image_base64 else None


def product_image_references(
    design: dict[str, Any] | None,
    limit: int,
    revision_text: str = "",
    *,
    matched_only: bool = False,
) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    if not design or limit <= 0:
        return references
    slots = list(design.get("grounder_output", {}).get("grounded_slots", []))
    normalized_revision = revision_text.lower()
    refresh_all = any(phrase in normalized_revision for phrase in ["refresh furniture", "every furniture", "all furniture", "catalogue list"])
    if matched_only and not refresh_all:
        slots = [
            slot
            for slot in slots
            if any(
                value and str(value).lower() in normalized_revision
                for value in [
                    slot.get("slot", {}).get("category"),
                    (slot.get("selected_item") or {}).get("item_id"),
                    (slot.get("selected_item") or {}).get("title"),
                ]
            )
        ]
    slots.sort(
        key=lambda slot: 0
        if any(
            value and str(value).lower() in normalized_revision
            for value in [
                slot.get("slot", {}).get("category"),
                (slot.get("selected_item") or {}).get("item_id"),
                (slot.get("selected_item") or {}).get("title"),
            ]
        )
        else 1
    )
    for slot in slots:
        item = slot.get("selected_item") or {}
        image_path = str(item.get("image_path") or "").lstrip("/")
        if not image_path.startswith("product-images/"):
            continue
        local_path = Path("public") / image_path
        try:
            image_bytes = local_path.read_bytes()
        except OSError:
            continue
        suffix = local_path.suffix.lower()
        mime_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        label = clean_prompt_part(
            f"exact {slot.get('slot', {}).get('category', 'product')} product {item.get('item_id', '')}: "
            f"{item.get('title', item.get('item_id', 'catalogue item'))}"
        )
        references.append((label, f"data:{mime_type};base64,{encoded}"))
        if len(references) >= limit:
            break
    return references


def product_match_candidates(
    design: dict[str, Any] | None,
    *,
    per_slot: int = 3,
    limit: int = 24,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    if not design:
        return candidates
    for grounded_slot in design.get("grounder_output", {}).get("grounded_slots", []):
        category = str(grounded_slot.get("slot", {}).get("category") or "item")
        slot_candidates = [
            grounded_slot.get("selected_item"),
            *(grounded_slot.get("alternatives") or []),
        ]
        added_for_slot = 0
        for item in slot_candidates:
            item_id = str((item or {}).get("item_id") or "")
            image_path = str((item or {}).get("image_path") or "").lstrip("/")
            if not item_id or item_id in seen_ids or not image_path.startswith("product-images/"):
                continue
            try:
                image_bytes = (APP_ROOT / "public" / image_path).read_bytes()
            except OSError:
                continue
            suffix = Path(image_path).suffix.lower()
            mime_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
            candidates.append(
                {
                    "category": category,
                    "placement_zone": grounded_slot.get("placement_zone"),
                    "item": dict(item),
                    "image_data_url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
                }
            )
            seen_ids.add(item_id)
            added_for_slot += 1
            if added_for_slot >= per_slot or len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break
    return candidates


async def edit_openai_image(prompt: str, image_references: list[tuple[str, str]]) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API")
    if not api_key:
        return None
    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, (label, data_url) in enumerate(image_references[:12]):
        if not data_url:
            continue
        mime_type, image_bytes = image_bytes_from_data_url(data_url)
        extension = "jpg" if mime_type == "image/jpeg" else mime_type.split("/")[-1]
        safe_label = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:48] or "reference"
        files.append(("image[]", (f"{index + 1}-{safe_label}.{extension}", image_bytes, mime_type)))
    if not files:
        return await generate_openai_image(prompt)
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            form_data = {
                "model": model,
                "prompt": prompt,
                "size": "1536x1024",
                "quality": os.environ.get("OPENAI_IMAGE_QUALITY", "medium"),
                "output_format": "jpeg",
            }
            if model != "gpt-image-2":
                form_data["input_fidelity"] = "high"
            response = await client.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {api_key}"},
                data=form_data,
                files=files,
            )
    except httpx.RequestError as exc:
        raise ImageServiceUnavailableError("OpenAI image editing could not be reached") from exc
    if response.status_code >= 400:
        raise typed_error(502, "image_generation_failed", "OpenAI image edit failed", error=response.text[:500])
    payload = response.json()
    image_base64 = payload.get("data", [{}])[0].get("b64_json")
    return f"data:image/jpeg;base64,{image_base64}" if image_base64 else None


def response_output_text(payload: dict[str, Any]) -> str | None:
    for output in payload.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    return None


def merge_observed_finish_schedule(
    proposed_schedule: list[dict[str, Any]],
    observed_finishes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed_by_category = {
        str(item.get("category", "")).strip().lower(): item
        for item in observed_finishes
        if isinstance(item, dict) and item.get("visible") is True
    }
    merged: list[dict[str, Any]] = []
    for proposed in proposed_schedule:
        item = dict(proposed)
        category = str(item.get("category", "")).strip()
        observed = observed_by_category.get(category.lower())
        if not observed:
            merged.append(item)
            continue
        colour_name = str(observed.get("colour_name", "")).strip()
        hex_code = str(observed.get("hex", "")).strip().upper()
        if not colour_name or not re.fullmatch(r"#[0-9A-F]{6}", hex_code):
            merged.append(item)
            continue
        item["colourName"] = colour_name
        item["hex"] = hex_code
        item["colourSource"] = "generated_image"
        bounding_box = observed.get("bounding_box")
        if isinstance(bounding_box, dict):
            coordinates = {
                key: int(bounding_box.get(key, 0))
                for key in ("x", "y", "width", "height")
                if isinstance(bounding_box.get(key), (int, float))
            }
            if (
                len(coordinates) == 4
                and coordinates["width"] > 0
                and coordinates["height"] > 0
                and all(0 <= value <= 1000 for value in coordinates.values())
                and coordinates["x"] + coordinates["width"] <= 1000
                and coordinates["y"] + coordinates["height"] <= 1000
            ):
                item["imageCrop"] = coordinates
        normalized_category = category.lower()
        if normalized_category == "wall paint":
            item["recommendation"] = f"{colour_name} washable low-sheen emulsion"
        elif normalized_category == "flooring":
            item["recommendation"] = f"{colour_name} matte wood or stone-look finish"
        elif normalized_category == "tiles":
            item["recommendation"] = f"{colour_name} matte large-format tile"
        merged.append(item)
    return merged


async def analyze_generated_finish_schedule(
    image_data_url: str,
    proposed_schedule: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API")
    categories = [
        str(item.get("category", "")).strip()
        for item in proposed_schedule
        if isinstance(item, dict) and item.get("category")
    ]
    if not api_key or not image_data_url or not categories:
        return proposed_schedule
    schema = {
        "type": "object",
        "properties": {
            "finishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "colour_name": {"type": "string"},
                        "hex": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
                        "visible": {"type": "boolean"},
                        "bounding_box": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "y": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "width": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "height": {"type": "integer", "minimum": 0, "maximum": 1000},
                            },
                            "required": ["x", "y", "width", "height"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["category", "colour_name", "hex", "visible", "bounding_box"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["finishes"],
        "additionalProperties": False,
    }
    prompt = (
        "Inspect this final rendered interior image and identify the dominant visible colour for each requested "
        "material category. Return the category names exactly as supplied. Estimate a representative RGB hex "
        "from the visible pixels and give it a concise professional paint or material colour name. Mark visible "
        "false when the category cannot actually be seen; do not infer a requested prompt colour that is absent "
        "from the rendered image. For every visible category, return a tight bounding box around its clearest "
        "appearance using x, y, width, and height normalized from 0 to 1000. Use four zeros when it is not visible. "
        f"Requested categories: {json.dumps(categories)}"
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini"),
                    "store": False,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {"type": "input_image", "image_url": image_data_url, "detail": "high"},
                            ],
                        }
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "observed_finish_colours",
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    "max_output_tokens": 900,
                },
            )
        if response.status_code >= 400:
            return proposed_schedule
        output_text = response_output_text(response.json())
        if not output_text:
            return proposed_schedule
        observed = json.loads(output_text).get("finishes", [])
        if not isinstance(observed, list):
            return proposed_schedule
        return merge_observed_finish_schedule(proposed_schedule, observed)
    except (httpx.RequestError, json.JSONDecodeError, TypeError, ValueError):
        return proposed_schedule


def reconcile_generated_products(
    design: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    observed_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    proposed = selected_product_snapshots(design)
    candidates_by_id = {
        str(candidate.get("item", {}).get("item_id") or ""): candidate
        for candidate in candidates
    }
    matches_by_category = {
        str(match.get("category") or "").strip().lower(): match
        for match in observed_matches
        if isinstance(match, dict)
    }
    reconciled: list[dict[str, Any]] = []
    for snapshot in proposed:
        category = str(snapshot.get("category") or "item")
        match = matches_by_category.get(category.lower())
        if not match or match.get("visible") is not True:
            reconciled.append({**snapshot, "imageMatch": "not_visible"})
            continue
        candidate = candidates_by_id.get(str(match.get("item_id") or ""))
        if not candidate or str(candidate.get("category") or "").lower() != category.lower():
            reconciled.append(snapshot)
            continue
        confidence = match.get("confidence")
        reconciled.append(
            {
                **candidate["item"],
                "category": category,
                "placement_zone": candidate.get("placement_zone") or snapshot.get("placement_zone"),
                "imageMatch": "closest_catalogue_match",
                "matchConfidence": round(float(confidence), 2) if isinstance(confidence, (int, float)) else None,
            }
        )
    return reconciled


async def analyze_generated_products(
    image_data_url: str,
    design: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    proposed = selected_product_snapshots(design)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API")
    candidates = product_match_candidates(design)
    if not api_key or not image_data_url or not candidates:
        return proposed
    candidate_ids = [str(candidate["item"].get("item_id")) for candidate in candidates]
    categories = list(dict.fromkeys(str(candidate["category"]) for candidate in candidates))
    schema = {
        "type": "object",
        "properties": {
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": categories},
                        "item_id": {"type": "string", "enum": candidate_ids},
                        "visible": {"type": "boolean"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["category", "item_id", "visible", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["products"],
        "additionalProperties": False,
    }
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Image 1 is the final generated room. Compare every clearly visible furniture or decor object "
                "against the labelled catalogue candidate images that follow. Return one result for each requested "
                "category. Choose only an item_id supplied for that same category, based on silhouette, proportions, "
                "material, and colour rather than the prompt's intended selection. If the category is not clearly "
                "visible in Image 1, mark visible false and use any supplied item_id for that category as a schema "
                f"placeholder. Requested categories: {json.dumps(categories)}"
            ),
        },
        {"type": "input_image", "image_url": image_data_url, "detail": "high"},
    ]
    for index, candidate in enumerate(candidates, start=2):
        item = candidate["item"]
        content.extend(
            [
                {
                    "type": "input_text",
                    "text": clean_prompt_part(
                        f"Image {index} candidate: category {candidate['category']}; item_id {item.get('item_id')}; "
                        f"title {item.get('title')}; material {item.get('material')}; colour {item.get('color')}."
                    ),
                },
                {"type": "input_image", "image_url": candidate["image_data_url"], "detail": "low"},
            ]
        )
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini"),
                    "store": False,
                    "input": [{"role": "user", "content": content}],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "generated_product_matches",
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    "max_output_tokens": 1200,
                },
            )
        if response.status_code >= 400:
            return proposed
        output_text = response_output_text(response.json())
        if not output_text:
            return proposed
        observed = json.loads(output_text).get("products", [])
        if not isinstance(observed, list):
            return proposed
        return reconcile_generated_products(design, candidates, observed)
    except (httpx.RequestError, json.JSONDecodeError, TypeError, ValueError):
        return proposed


def run_design_for_session(session_id: str, max_retries: int, design_id: str | None = None) -> dict[str, Any]:
    state = state_store.get(session_id)
    if state is None or state.brief is None:
        raise typed_error(404, "not_found", "session not found")
    try:
        result = run_agent_loop(
            state.brief,
            planner_client=planner_client(state.brief),
            catalogue_path=CATALOGUE_PATH,
            chroma_path=CHROMA_PATH,
            max_retries=max_retries,
        )
    except RuntimeError as exc:
        if str(exc) == "missing_api_key":
            raise typed_error(503, "missing_api_key", "planner API key is not configured on the backend") from exc
        raise typed_error(500, "graph_failure", "agent graph failed") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise typed_error(500, "graph_failure", "agent graph failed", error=exc.__class__.__name__) from exc

    resolved_design_id = design_id or f"design-{uuid4().hex[:12]}"
    payload = serializable_design(resolved_design_id, session_id, state.brief, result)
    design_store.save(resolved_design_id, payload)
    state.attempt_log = payload["attempt_log"]
    if result.status == "failed":
        raise typed_error(409, "retry_exhausted", "agent retry cap exhausted", design=payload)
    return payload


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/auth/signup", response_model=AuthResponse)
def sign_up(payload: SignUpRequest, response: Response) -> AuthResponse:
    user = auth_store.create_user(payload.name, payload.email, payload.password)
    set_auth_cookie(response, auth_store.create_session(user["id"]))
    return AuthResponse(user=AuthUser(**user))


@app.post("/api/auth/login", response_model=AuthResponse)
def log_in(payload: LoginRequest, response: Response) -> AuthResponse:
    user = auth_store.authenticate(payload.email, payload.password)
    if user is None:
        raise typed_error(401, "invalid_credentials", "email or password is incorrect")
    set_auth_cookie(response, auth_store.create_session(user["id"]))
    return AuthResponse(user=AuthUser(**user))


@app.get("/api/auth/me", response_model=AuthResponse)
def auth_me(request: Request) -> AuthResponse:
    user = authenticated_user(request)
    return AuthResponse(user=AuthUser(**user))


@app.patch("/api/auth/profile", response_model=AuthResponse)
def update_profile(payload: UpdateProfileRequest, request: Request) -> AuthResponse:
    user = authenticated_user(request)
    updated = auth_store.update_profile(
        user["id"],
        name=payload.name,
        location=payload.location,
        home_type=payload.home_type,
        preferred_units=payload.preferred_units,
    )
    return AuthResponse(user=AuthUser(**updated))


@app.post("/api/auth/logout", response_model=LogoutResponse)
def log_out(request: Request, response: Response) -> LogoutResponse:
    auth_store.revoke(request.cookies.get(AUTH_COOKIE_NAME))
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return LogoutResponse(status="signed_out")


@app.post("/api/session", response_model=SessionResponse)
def create_session(http_request: Request, request: SessionRequest | None = None) -> SessionResponse:
    session_id = f"local-{uuid4().hex[:12]}"
    if request and request.brief:
        brief = request.brief
    elif request and request.message:
        parsed = parse_room_brief_text(request.message)
        brief = create_room_brief(**parsed)
    else:
        brief = create_room_brief()
    state = state_store.create(session_id, brief)
    signed_in_user = request_user(http_request)
    if signed_in_user:
        session_users[session_id] = signed_in_user["id"]
    elif request and request.user_id:
        session_users[session_id] = request.user_id
    if request and request.project_id:
        session_projects[session_id] = {
            "project_id": request.project_id,
            "project_name": request.project_name or brief.room_type.replace("_", " ").title(),
        }
    else:
        session_projects[session_id] = {
            "project_id": session_id,
            "project_name": request.project_name if request and request.project_name else brief.room_type.replace("_", " ").title(),
        }
    if request and request.message:
        state = state_store.append_message(session_id, "user", request.message)
    return SessionResponse(session_id=session_id, state=dict(to_graph_state(state)))


@app.get("/api/session/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, request: Request) -> SessionResponse:
    assert_session_owner(session_id, request_user(request))
    state = state_store.get(session_id)
    if state is None:
        raise typed_error(404, "not_found", "session not found")
    return SessionResponse(session_id=session_id, state=dict(to_graph_state(state)))


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    assert_session_owner(payload.session_id, request_user(request))
    state = state_store.get(payload.session_id)
    if state is None:
        raise typed_error(404, "not_found", "session not found")
    state_store.append_message(payload.session_id, "user", payload.message)
    design = run_design_for_session(payload.session_id, payload.max_retries)
    state_store.append_message(payload.session_id, "assistant", f"Design {design['design_id']} completed.")
    design["chat_messages"] = list(state_store.get(payload.session_id).messages)
    design_store.save(str(design["design_id"]), design)
    return ChatResponse(state="passed", design=design)


@app.get("/api/designs", response_model=DesignListResponse)
def list_designs(
    request: Request,
    user_id: str | None = Query(default=None, min_length=1, max_length=120),
    project_id: str | None = Query(default=None, min_length=1, max_length=120),
) -> DesignListResponse:
    designs = design_store.values()
    signed_in_user = request_user(request)
    owner_id = signed_in_user["id"] if signed_in_user else user_id
    if owner_id:
        designs = [design for design in designs if design.get("user_id") == owner_id]
    if project_id:
        designs = [design for design in designs if (design.get("project_id") or design.get("session_id")) == project_id]
    summaries = sorted(
        (summarize_design(design) for design in designs),
        key=lambda summary: summary.generated_at,
        reverse=True,
    )
    return DesignListResponse(designs=summaries, count=len(summaries))


@app.delete("/api/projects/{project_id}", response_model=DeleteProjectResponse)
def delete_project(project_id: str, request: Request) -> DeleteProjectResponse:
    user = authenticated_user(request)
    deleted_designs = design_store.delete_project(project_id, user["id"])
    if not deleted_designs:
        raise typed_error(404, "not_found", "project not found")
    for design in deleted_designs:
        session_id = str(design.get("session_id") or "")
        if not session_id:
            continue
        state_store.delete(session_id)
        session_users.pop(session_id, None)
        session_projects.pop(session_id, None)
    return DeleteProjectResponse(status="deleted", deleted_designs=len(deleted_designs))


@app.get("/api/design/{design_id}", response_model=DesignResponse)
def get_design(design_id: str, request: Request) -> DesignResponse:
    stored_design = design_store.get(design_id)
    if stored_design is None:
        raise typed_error(404, "not_found", "design not found")
    design = deepcopy(stored_design)
    assert_design_owner(design, request_user(request))
    grounded_slots = list(design.get("grounder_output", {}).get("grounded_slots", []))
    failed_slots = [slot for slot in grounded_slots if not slot.get("selected_item")]
    if failed_slots and design.get("room_brief"):
        recovered = ground_design(
            design["room_brief"],
            [slot["slot"] for slot in failed_slots],
            catalogue_path=CATALOGUE_PATH,
            chroma_path=CHROMA_PATH,
        ).model_dump(mode="json")
        recovered_by_id = {
            str(slot.get("slot", {}).get("slot_id") or ""): slot
            for slot in recovered.get("grounded_slots", [])
            if slot.get("selected_item")
        }
        if recovered_by_id:
            design["grounder_output"]["grounded_slots"] = [
                recovered_by_id.get(str(slot.get("slot", {}).get("slot_id") or ""), slot)
                for slot in grounded_slots
            ]
    if design.get("room_brief") and design.get("grounder_output"):
        refreshed_verdict = critique_design(
            design["room_brief"],
            design["grounder_output"],
            catalogue_path=CATALOGUE_PATH,
        ).model_dump(mode="json")
        if refreshed_verdict != design.get("critic_verdict"):
            design["critic_verdict"] = refreshed_verdict
        if refreshed_verdict.get("passed") and design.get("status") == "failed":
            design["status"] = "passed"
    history, recovered_sources = project_concept_history(design)
    changed = (
        design.get("critic_verdict") != stored_design.get("critic_verdict")
        or design.get("grounder_output") != stored_design.get("grounder_output")
        or design.get("status") != stored_design.get("status")
    )
    if history and history != design.get("concept_history"):
        design["concept_history"] = history
        changed = True
    if recovered_sources and not design.get("source_images"):
        design["source_images"] = recovered_sources[:2]
        changed = True
    if changed:
        design_store.save(design_id, design)
    return DesignResponse(design=design)


@app.post("/api/concept-image", response_model=ConceptImageResponse)
async def create_concept_image(payload: ConceptImageRequest, request: Request) -> ConceptImageResponse:
    existing_design: dict[str, Any] | None = None
    if payload.design_id:
        existing_design = design_store.get(payload.design_id)
        if existing_design:
            assert_design_owner(existing_design, request_user(request))
            existing_design = dict(existing_design)
            project_history, recovered_sources = project_concept_history(existing_design)
            if project_history:
                existing_design["concept_history"] = project_history
            if recovered_sources and not existing_design.get("source_images"):
                existing_design["source_images"] = recovered_sources[:2]
            design_store.save(str(existing_design["design_id"]), existing_design)

    uploaded_sources = [image for image in payload.photo_data_urls if image]
    if existing_design and uploaded_sources:
        existing_design["source_images"] = uploaded_sources[:2]
        design_store.save(str(existing_design["design_id"]), existing_design)
    saved_sources = list((existing_design or {}).get("source_images") or [])
    source_images = uploaded_sources[:2] or saved_sources[:2]
    history = list((existing_design or {}).get("concept_history") or [])
    base_revision = next(
        (entry for entry in history if entry.get("revision_id") == payload.base_revision_id),
        None,
    )
    if payload.base_revision_id and base_revision is None:
        raise typed_error(422, "invalid_revision", "selected design version was not found")
    previous_image = (base_revision or (existing_design or {}).get("concept_image") or {}).get("image_data_url")
    revision_text = payload.revision_text or str((existing_design or {}).get("last_revision_request") or "")
    if revision_text != payload.revision_text:
        payload = payload.model_copy(update={"revision_text": revision_text})

    references: list[tuple[str, str]] = []
    has_previous_image = bool(previous_image and revision_text)
    if has_previous_image:
        references.append(("selected saved design version; primary pixel-level edit target", str(previous_image)))
    if source_images:
        references.append(("original room photo; architecture and camera source of truth", source_images[0]))
    remaining_reference_slots = max(0, 12 - len(references))
    references.extend(
        product_image_references(
            payload.grounded_design or existing_design,
            remaining_reference_slots,
            revision_text,
            matched_only=False,
        )
    )
    reference_labels = [f"Image {index + 1}: {label}" for index, (label, _) in enumerate(references)]
    prompt = build_concept_prompt(
        payload,
        has_source_image=bool(source_images),
        has_previous_image=has_previous_image,
        reference_labels=reference_labels,
    )
    image_service_note: str | None = None
    try:
        image_data_url = await edit_openai_image(prompt, references) if references else await generate_openai_image(prompt)
    except ImageServiceUnavailableError:
        image_data_url = None
        image_service_note = (
            "Your design request was saved, but the OpenAI image service could not be reached. "
            "The current image is unchanged; retry the revision when the image service is available."
        )
    image_source = "revision_from_original_and_current" if has_previous_image and source_images else "revision_from_current" if has_previous_image else "uploaded_room_photo" if source_images else "text_prompt"
    if image_data_url:
        finish_schedule, selected_products = await asyncio.gather(
            analyze_generated_finish_schedule(image_data_url, payload.finish_schedule),
            analyze_generated_products(image_data_url, payload.grounded_design or existing_design),
        )
        revision_id = f"revision-{uuid4().hex[:12]}"
        generated_at = datetime.now(UTC).isoformat()
        history = list((existing_design or {}).get("concept_history") or concept_history_with_current(existing_design))
        revision_entry = {
            "revision_id": revision_id,
            "version": len(history) + 1,
            "label": "Original design" if not history else f"Version {len(history) + 1}",
            "revision_text": revision_text or "Initial generated design",
            "base_revision_id": payload.base_revision_id,
            "mode": "generated",
            "image_prompt": prompt,
            "image_data_url": image_data_url,
            "generated_at": generated_at,
            "source": image_source,
            "selected_products": selected_products,
            "finish_schedule": finish_schedule,
            "notes": [
                "Edited from the current approved design and original room reference."
                if has_previous_image
                else "Initial generated design created from the approved room and product references."
            ],
        }
        history.append(revision_entry)
        if payload.design_id:
            design = design_store.get(payload.design_id)
            if design:
                if uploaded_sources:
                    design["source_images"] = uploaded_sources[:2]
                design["concept_image"] = revision_entry
                design["concept_history"] = history
                design["last_revision_request"] = ""
                design_store.save(payload.design_id, design)
        return ConceptImageResponse(
            mode="generated",
            image_prompt=prompt,
            image_data_url=image_data_url,
            revision_id=revision_id,
            concept_history=history,
            notes=[
                "Edited from the original room and current approved design without changing the room shell."
                if has_previous_image
                else "Edited from the uploaded room photo with the configured OpenAI image model."
                if source_images
                else "Generated with the configured OpenAI image model."
            ],
        )
    history = list((existing_design or {}).get("concept_history") or concept_history_with_current(existing_design))
    if payload.design_id:
        design = design_store.get(payload.design_id)
        if design:
            if uploaded_sources:
                design["source_images"] = uploaded_sources[:2]
            if not (design.get("concept_image") or {}).get("image_data_url"):
                design["concept_image"] = {
                    "mode": "prompt_only",
                    "image_prompt": prompt,
                    "image_data_url": None,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "source": image_source,
                }
            else:
                design["pending_concept_prompt"] = prompt
            design_store.save(payload.design_id, design)
    return ConceptImageResponse(
        mode="prompt_only",
        image_prompt=prompt,
        image_data_url=None,
        concept_history=history,
        notes=[
            image_service_note
            or (
                "Set OPENAI_API_KEY or OPENAI_API on the backend to edit the uploaded room photo. Demo mode returns the exact prompt that will be sent."
                if source_images or has_previous_image
                else "Set OPENAI_API_KEY or OPENAI_API on the backend to generate the final concept image. Demo mode returns the exact prompt that will be sent."
            )
        ],
    )


@app.post("/api/design/{design_id}/revise", response_model=DesignResponse)
def revise_design(design_id: str, payload: ReviseRequest, request: Request) -> DesignResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    assert_design_owner(design, request_user(request))
    session_id = payload.session_id or str(design["session_id"])
    if state_store.get(session_id) is None:
        room_brief = design.get("room_brief")
        if not room_brief:
            raise typed_error(404, "not_found", "session not found")
        state_store.create(session_id, RoomBrief(**room_brief))
        for message in design.get("chat_messages", []):
            if message.get("role") in {"user", "assistant"} and message.get("content"):
                state_store.append_message(session_id, str(message["role"]), str(message["content"]))
    if design.get("user_id"):
        session_users[session_id] = str(design["user_id"])
    session_projects[session_id] = {
        "project_id": str(design.get("project_id") or session_id),
        "project_name": str(design.get("project_name") or design.get("room_brief", {}).get("room_type", "Room")).replace("_", " ").title(),
    }
    state_store.append_message(session_id, "user", payload.message)
    previous_grounded_slots = list(design.get("grounder_output", {}).get("grounded_slots", []))
    refresh_categories = requested_product_categories(payload.message, previous_grounded_slots)
    if payload.refresh_products or refresh_categories:
        room_brief = RoomBrief(**design["room_brief"])
        design_slots = design.get("designer_output", {}).get("slots", [])
        if not design_slots:
            raise typed_error(422, "invalid_design", "saved design has no furniture slots to refresh")
        history = concept_history_with_current(design)
        if history:
            design["concept_history"] = history
        refreshed = ground_design(
            room_brief,
            design_slots,
            catalogue_path=CATALOGUE_PATH,
            chroma_path=CHROMA_PATH,
        )
        refreshed_output = refreshed.model_dump(mode="json")
        refreshed_output["grounded_slots"] = synchronize_refreshed_products(
            previous_grounded_slots,
            refreshed_output["grounded_slots"],
            payload.message,
        )
        design["grounder_output"] = refreshed_output
        design["critic_verdict"] = critique_design(
            design["room_brief"],
            design["grounder_output"],
            catalogue_path=CATALOGUE_PATH,
        ).model_dump(mode="json")
        assistant_message = "I refreshed every furniture match for this room and will synchronize the image with the corrected catalogue list."
    else:
        assistant_message = "I will apply that as a focused visual revision while preserving the room and approved shopping list."
    state_store.append_message(session_id, "assistant", assistant_message)
    design["last_revision_request"] = payload.message
    design["chat_messages"] = list(state_store.get(session_id).messages)
    design["generated_at"] = datetime.now(UTC).isoformat()
    design_store.save(design_id, design)
    return DesignResponse(design=design)


@app.post("/api/design/{design_id}/select-item", response_model=DesignResponse)
def select_design_item(design_id: str, payload: SelectItemRequest, request: Request) -> DesignResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    assert_design_owner(design, request_user(request))
    grounded_slots = design.get("grounder_output", {}).get("grounded_slots", [])
    grounded_slot = next((slot for slot in grounded_slots if slot.get("slot", {}).get("slot_id") == payload.slot_id), None)
    if grounded_slot is None:
        raise typed_error(404, "not_found", "furniture slot not found")
    current_item = grounded_slot.get("selected_item")
    alternatives = grounded_slot.get("alternatives", [])
    replacement = next((item for item in alternatives if item.get("item_id") == payload.item_id), None)
    if replacement is None:
        raise typed_error(422, "invalid_selection", "item is not an approved alternative for this slot")
    grounded_slot["selected_item"] = replacement
    grounded_slot["alternatives"] = [current_item, *[item for item in alternatives if item.get("item_id") != payload.item_id]]
    grounded_slot["alternatives"] = [item for item in grounded_slot["alternatives"] if item]
    verdict = critique_design(design["room_brief"], design["grounder_output"], catalogue_path=CATALOGUE_PATH)
    design["critic_verdict"] = verdict.model_dump(mode="json")
    chat_messages = list(design.get("chat_messages", []))
    chat_messages.extend([
        {"role": "user", "content": f"Use {replacement.get('title', payload.item_id)} for the {grounded_slot.get('slot', {}).get('category', 'furniture')} selection."},
        {"role": "assistant", "content": "Furniture updated. Room fit, sourceability, Vastu guidance, and budget were checked again."},
    ])
    design["chat_messages"] = chat_messages
    design["generated_at"] = datetime.now(UTC).isoformat()
    design_store.save(design_id, design)
    return DesignResponse(design=design)


@app.get("/api/catalogue/search", response_model=CatalogueSearchResponse)
def catalogue_search(
    q: str = Query(..., min_length=1),
    category: str | None = None,
    max_width_cm: float | None = Query(default=None, gt=0),
    max_depth_cm: float | None = Query(default=None, gt=0),
    max_price_inr: int | None = Query(default=None, gt=0),
    k: int = Query(default=5, ge=1, le=20),
) -> CatalogueSearchResponse:
    try:
        results = search_items(
            q,
            category=category,
            max_width_cm=max_width_cm,
            max_depth_cm=max_depth_cm,
            max_price_inr=max_price_inr,
            k=k,
            chroma_path=CHROMA_PATH,
        )
    except Exception as exc:
        raise typed_error(500, "graph_failure", "catalogue search failed", error=exc.__class__.__name__) from exc
    if not results:
        raise typed_error(404, "no_catalogue_results", "no catalogue items matched the query")
    return CatalogueSearchResponse(results=results, count=len(results))


@app.get("/api/export/{design_id}", response_model=ExportResponse)
def export_design(
    design_id: str,
    request: Request,
    revision_id: str | None = Query(default=None, min_length=1, max_length=160),
) -> ExportResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    assert_design_owner(design, request_user(request))
    history, recovered_sources = project_concept_history(design)
    selected_revision = next((revision for revision in history if revision.get("revision_id") == revision_id), None)
    if revision_id and selected_revision is None:
        raise typed_error(422, "invalid_revision", "selected design version was not found")

    current_selected = [
        slot["selected_item"] for slot in design["grounder_output"]["grounded_slots"] if slot.get("selected_item")
    ]
    if selected_revision and selected_revision.get("selected_products"):
        item_index = project_product_index(design)
        selected = []
        for snapshot in selected_revision["selected_products"]:
            item_id = str(snapshot.get("item_id") or "")
            item = {**item_index.get(item_id, {}), **snapshot}
            if not item_id or item.get("price_inr") is None:
                raise typed_error(422, "revision_data_incomplete", "selected version is missing saved product details")
            selected.append(item)
    else:
        selected = current_selected
    total_price = sum(int(item["price_inr"]) for item in selected)
    stored_total = int(design["critic_verdict"]["total_price_inr"])
    if not selected_revision and total_price != stored_total:
        raise typed_error(500, "graph_failure", "stored design total does not match selected item prices")
    room_facts = design["planner_output"]["room_facts"]
    budget = int(room_facts["budget_inr"])
    exported_total = total_price if selected_revision else stored_total
    exported_image = selected_revision or (design.get("concept_image") or {})
    return ExportResponse(
        design_id=design_id,
        project_name=str(design.get("project_name") or room_facts.get("room_type", "Design brief")).replace("_", " ").title(),
        generated_at=str((selected_revision or {}).get("generated_at") or design["generated_at"]),
        revision_id=str(selected_revision.get("revision_id")) if selected_revision else None,
        concept_image_data_url=exported_image.get("image_data_url"),
        source_image_data_url=next(iter(design.get("source_images") or recovered_sources), None),
        revision_label=selected_revision.get("label") if selected_revision else exported_image.get("label"),
        room_brief=room_facts,
        user_requirements={
            "style_words": room_facts.get("style_words", []),
            "constraints": design["planner_output"].get("constraints", []),
            "missing_questions": design["planner_output"].get("missing_questions", []),
        },
        selected_items=selected,
        finish_schedule=list(exported_image.get("finish_schedule") or []),
        total_price_inr=exported_total,
        budget_summary={
            "budget_inr": budget,
            "total_price_inr": exported_total,
            "remaining_inr": budget - exported_total,
            "status": "pass" if exported_total <= budget else "fail",
        },
        fit_notes=design["critic_verdict"]["fit"]["notes"],
        vastu_summary=design["critic_verdict"]["vastu"],
        attribution="Amazon Berkeley Objects (ABO); INR prices are curated indicative demo values.",
    )
