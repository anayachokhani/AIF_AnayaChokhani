from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from formaos.agents.graph_loop import AgentLoopResult, run_agent_loop
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


CATALOGUE_PATH = Path("data/curated/abo_mvp_catalogue_with_images.csv")
CHROMA_PATH = Path("data/vectorstores/chroma")

app = FastAPI(title="FormaOS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_store = InMemoryStateStore()
design_store: dict[str, dict[str, Any]] = {}
planner_client_override: PlannerClient | None = None


class DemoPlannerClient:
    def __init__(self, brief: RoomBrief) -> None:
        self.brief = brief

    def complete(self, messages: list[dict[str, str]]) -> str:
        dims = brief_dimensions_cm(self.brief)
        categories = ["table", "rug", "lamp", "planter"]
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


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    max_retries: int = Field(default=2, ge=0, le=3)


class ReviseRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(default="Revise this design.", min_length=1)
    max_retries: int = Field(default=2, ge=0, le=3)


class ErrorDetail(BaseModel):
    code: str
    message: str
    errors: list[dict[str, Any]] | None = None
    error: str | None = None
    design: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str


class SessionResponse(BaseModel):
    session_id: str
    state: dict[str, Any]


class ChatResponse(BaseModel):
    state: str
    design: dict[str, Any]


class DesignResponse(BaseModel):
    design: dict[str, Any]


class CatalogueSearchResponse(BaseModel):
    results: list[dict[str, Any]]
    count: int


class ExportResponse(BaseModel):
    design_id: str
    generated_at: str
    room_brief: dict[str, Any]
    user_requirements: dict[str, Any]
    selected_items: list[dict[str, Any]]
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


def planner_client(brief: RoomBrief | None = None) -> PlannerClient | None:
    if planner_client_override is None and brief is not None and os.environ.get("FORMAOS_DEMO_PLANNER") == "1":
        return DemoPlannerClient(brief)
    return planner_client_override


def serializable_design(design_id: str, session_id: str, result: AgentLoopResult) -> dict[str, Any]:
    return {
        "design_id": design_id,
        "session_id": session_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": result.status,
        "planner_output": result.planner_output.model_dump(mode="json"),
        "designer_output": result.designer_output.model_dump(mode="json"),
        "grounder_output": result.grounder_output.model_dump(mode="json"),
        "critic_verdict": result.critic_verdict.model_dump(mode="json"),
        "attempt_log": [entry.model_dump(mode="json") for entry in result.attempt_log],
        "retries_used": result.retries_used,
        "max_retries": result.max_retries,
    }


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
    payload = serializable_design(resolved_design_id, session_id, result)
    design_store[resolved_design_id] = payload
    state.attempt_log = payload["attempt_log"]
    if result.status == "failed":
        raise typed_error(409, "retry_exhausted", "agent retry cap exhausted", design=payload)
    return payload


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/session", response_model=SessionResponse)
def create_session(request: SessionRequest | None = None) -> SessionResponse:
    session_id = f"local-{uuid4().hex[:12]}"
    if request and request.brief:
        brief = request.brief
    elif request and request.message:
        parsed = parse_room_brief_text(request.message)
        brief = create_room_brief(**parsed)
    else:
        brief = create_room_brief()
    state = state_store.create(session_id, brief)
    if request and request.message:
        state = state_store.append_message(session_id, "user", request.message)
    return SessionResponse(session_id=session_id, state=dict(to_graph_state(state)))


@app.get("/api/session/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    state = state_store.get(session_id)
    if state is None:
        raise typed_error(404, "not_found", "session not found")
    return SessionResponse(session_id=session_id, state=dict(to_graph_state(state)))


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    state = state_store.get(request.session_id)
    if state is None:
        raise typed_error(404, "not_found", "session not found")
    state_store.append_message(request.session_id, "user", request.message)
    design = run_design_for_session(request.session_id, request.max_retries)
    state_store.append_message(request.session_id, "assistant", f"Design {design['design_id']} completed.")
    return ChatResponse(state="passed", design=design)


@app.get("/api/design/{design_id}", response_model=DesignResponse)
def get_design(design_id: str) -> DesignResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    return DesignResponse(design=design)


@app.post("/api/design/{design_id}/revise", response_model=DesignResponse)
def revise_design(design_id: str, request: ReviseRequest) -> DesignResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    session_id = request.session_id or str(design["session_id"])
    if state_store.get(session_id) is None:
        raise typed_error(404, "not_found", "session not found")
    state_store.append_message(session_id, "user", request.message)
    revised = run_design_for_session(session_id, request.max_retries, design_id=design_id)
    return DesignResponse(design=revised)


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
def export_design(design_id: str) -> ExportResponse:
    design = design_store.get(design_id)
    if design is None:
        raise typed_error(404, "not_found", "design not found")
    selected = [
        slot["selected_item"]
        for slot in design["grounder_output"]["grounded_slots"]
        if slot.get("selected_item")
    ]
    total_price = sum(int(item["price_inr"]) for item in selected)
    stored_total = int(design["critic_verdict"]["total_price_inr"])
    if total_price != stored_total:
        raise typed_error(500, "graph_failure", "stored design total does not match selected item prices")
    room_facts = design["planner_output"]["room_facts"]
    budget = int(room_facts["budget_inr"])
    return ExportResponse(
        design_id=design_id,
        generated_at=str(design["generated_at"]),
        room_brief=room_facts,
        user_requirements={
            "style_words": room_facts.get("style_words", []),
            "constraints": design["planner_output"].get("constraints", []),
            "missing_questions": design["planner_output"].get("missing_questions", []),
        },
        selected_items=selected,
        total_price_inr=stored_total,
        budget_summary={
            "budget_inr": budget,
            "total_price_inr": stored_total,
            "remaining_inr": budget - stored_total,
            "status": design["critic_verdict"]["budget"]["status"],
        },
        fit_notes=design["critic_verdict"]["fit"]["notes"],
        vastu_summary=design["critic_verdict"]["vastu"],
        attribution="Amazon Berkeley Objects (ABO); INR prices are curated indicative demo values.",
    )
