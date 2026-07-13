from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Direction = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"]
ResponseState = Literal[
    "waiting",
    "planning",
    "designing",
    "grounding",
    "checking",
    "revising",
    "passed",
    "failed",
    "error",
]


class Units(str, Enum):
    FT = "ft"
    CM = "cm"
    M = "m"


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


class RoomBrief(BaseModel):
    room_type: str = Field(..., min_length=1)
    width: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    units: Units
    budget_inr: int = Field(..., gt=0)
    style_words: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    vastu_enabled: bool = False
    main_door_direction: Direction | None = None
    compass_direction: Direction | None = None

    @model_validator(mode="after")
    def dimensions_are_reasonable(self) -> "RoomBrief":
        if self.units == Units.FT and (self.width > 80 or self.depth > 80):
            raise ValueError("room dimensions in feet look too large")
        if self.units == Units.CM and (self.width < 100 or self.depth < 100):
            raise ValueError("room dimensions in centimeters look too small")
        return self


class DesignSlot(BaseModel):
    slot_id: str
    category: str
    quantity: int = Field(default=1, ge=1)
    target_width_cm: float | None = Field(default=None, gt=0)
    target_depth_cm: float | None = Field(default=None, gt=0)
    style_text: str = ""
    budget_share: float = Field(..., ge=0, le=1)
    must_have_constraints: list[str] = Field(default_factory=list)
    placement_hint: Direction | None = None


class CatalogueItem(BaseModel):
    item_id: str
    title: str
    product_type: str
    width_cm: float = Field(..., gt=0)
    depth_cm: float = Field(..., gt=0)
    height_cm: float | None = Field(default=None, gt=0)
    material: str | None = None
    color: str | None = None
    style_text: str = ""
    price_inr: int = Field(..., gt=0)
    image_path: str | None = None
    image_available: bool = False
    source_url: str | None = None
    source_dataset: str = "demo_catalogue"
    price_note: str = "curated indicative demo price"
    placement_zone: Direction | None = None


class AttemptLogEntry(BaseModel):
    attempt: int
    state: ResponseState
    notes: list[str] = Field(default_factory=list)
    changed_slots: list[str] = Field(default_factory=list)
    changed_items: list[str] = Field(default_factory=list)


class GroundedDesign(BaseModel):
    design_id: str
    brief: RoomBrief
    slots: list[DesignSlot]
    selected_items: list[CatalogueItem]
    alternatives: dict[str, list[CatalogueItem]] = Field(default_factory=dict)
    total_price_inr: int
    fit_status: CheckStatus
    budget_status: CheckStatus
    sourceability_status: CheckStatus
    vastu_status: CheckStatus = CheckStatus.SKIPPED
    fit_notes: list[str] = Field(default_factory=list)
    vastu_notes: list[str] = Field(default_factory=list)
    attempt_log: list[AttemptLogEntry] = Field(default_factory=list)
