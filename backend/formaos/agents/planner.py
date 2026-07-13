from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from formaos.contracts import RoomBrief
from formaos.room_state import brief_dimensions_cm


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
ALLOWED_NEED_CATEGORIES = {
    "sofa",
    "loveseat",
    "bed",
    "cabinet",
    "storage",
    "table",
    "desk",
    "chair",
    "rug",
    "lamp",
    "mirror",
    "planter",
}


class RoomFacts(BaseModel):
    room_type: str
    width_cm: float = Field(..., gt=0)
    depth_cm: float = Field(..., gt=0)
    budget_inr: int = Field(..., gt=0)
    style_words: list[str] = Field(default_factory=list)


class PlannerNeed(BaseModel):
    category: str
    purpose: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1, le=8)
    priority: int = Field(..., ge=1, le=5)
    max_width_cm: float | None = Field(default=None, gt=0)
    max_depth_cm: float | None = Field(default=None, gt=0)
    budget_share: float = Field(..., gt=0, le=1)
    style_tags: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @property
    def normalized_category(self) -> str:
        return self.category.strip().lower()

    def model_post_init(self, __context: Any) -> None:
        self.category = self.normalized_category
        if self.category not in ALLOWED_NEED_CATEGORIES:
            raise ValueError(f"unsupported need category: {self.category}")


class PlannerOutput(BaseModel):
    room_facts: RoomFacts
    constraints: list[str] = Field(default_factory=list)
    needs_list: list[PlannerNeed] = Field(..., min_length=2, max_length=10)
    missing_questions: list[str] = Field(default_factory=list)


class PlannerClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str:
        ...


class PlannerValidationError(RuntimeError):
    def __init__(self, message: str, *, raw_response: str, original_error: Exception) -> None:
        super().__init__(message)
        self.code = "planner_validation_failed"
        self.raw_response = raw_response
        self.original_error = original_error


class OpenRouterPlannerClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 45.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API", "")
        self.model = model
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("missing_api_key")

    def complete(self, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"])


def build_planner_prompt(brief: RoomBrief, validation_error: str | None = None) -> list[dict[str, str]]:
    dims = brief_dimensions_cm(brief)
    schema_hint = {
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
                "category": "sofa",
                "purpose": "primary seating",
                "quantity": 1,
                "priority": 1,
                "max_width_cm": 220,
                "max_depth_cm": 100,
                "budget_share": 0.35,
                "style_tags": brief.style_words,
                "constraints": brief.constraints,
            }
        ],
        "missing_questions": [],
    }
    system = (
        "You are the FormaOS Planner node. Return only strict JSON. "
        "Preserve the room facts, budget, style words, and constraints exactly. "
        "Create a practical furniture needs list for later retrieval. "
        f"Allowed categories: {', '.join(sorted(ALLOWED_NEED_CATEGORIES))}."
    )
    user = (
        "Build a room planning JSON object matching this shape. "
        f"RoomBrief: {brief.model_dump(mode='json')}. "
        f"Centimeter dimensions: {dims.model_dump()}. "
        f"Example shape: {json.dumps(schema_hint)}."
    )
    if validation_error:
        user += f" Previous response failed validation: {validation_error}. Retry with valid JSON only."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_planner_json(raw_content: str) -> PlannerOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValidationError.from_exception_data(
            "PlannerOutput",
            [{"type": "value_error", "loc": ("__root__",), "msg": "invalid JSON", "input": raw_content, "ctx": {"error": exc}}],
        ) from exc
    return PlannerOutput.model_validate(payload)


def validate_preserves_brief(output: PlannerOutput, brief: RoomBrief) -> PlannerOutput:
    dims = brief_dimensions_cm(brief)
    facts = output.room_facts
    errors: list[str] = []
    if facts.room_type != brief.room_type:
        errors.append("room_type changed")
    if facts.width_cm != dims.width_cm or facts.depth_cm != dims.depth_cm:
        errors.append("room dimensions changed")
    if facts.budget_inr != brief.budget_inr:
        errors.append("budget changed")
    if facts.style_words != brief.style_words:
        errors.append("style words changed")
    if errors:
        raise ValueError("; ".join(errors))
    return output


def plan_room(brief: RoomBrief, client: PlannerClient | None = None) -> PlannerOutput:
    planner_client = client or OpenRouterPlannerClient()
    first_raw = planner_client.complete(build_planner_prompt(brief))
    try:
        return validate_preserves_brief(parse_planner_json(first_raw), brief)
    except (ValidationError, ValueError) as first_error:
        retry_raw = planner_client.complete(build_planner_prompt(brief, str(first_error)))
        try:
            return validate_preserves_brief(parse_planner_json(retry_raw), brief)
        except (ValidationError, ValueError) as retry_error:
            raise PlannerValidationError(
                "Planner response failed validation after retry.",
                raw_response=retry_raw,
                original_error=retry_error,
            ) from retry_error
