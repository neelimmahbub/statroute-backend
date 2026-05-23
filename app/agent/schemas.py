from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EmergencyInput(BaseModel):
    """Raw API body from POST /api/emergency — unstructured alert text only."""

    model_config = ConfigDict(strict=True, extra="forbid")

    message: str


class EmergencyRequest(BaseModel):
    """Structured fields after Gemini parse + Pydantic validation — not a route param."""

    model_config = ConfigDict(strict=True, extra="forbid")

    hospital: str
    item: str
    quantity: int = Field(gt=0)
    urgency: Literal["Critical", "High", "Medium"]


class SupplierNode(BaseModel):
    """Hospital with available stock; id and node are both graph keys (hospital name)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    node: str
    available_qty: int = Field(ge=0)
    x: float
    y: float


class SupplierRoute(BaseModel):
    """One supplier leg: allocated quantity and shortest path from destination."""

    model_config = ConfigDict(strict=True, extra="forbid")

    supplier_id: str
    quantity_allocated: int = Field(gt=0)
    path: list[str]
    distance: float = Field(ge=0)


class RouteResult(BaseModel):
    """Full routing outcome; partial=True when multiple suppliers fulfill the request."""

    model_config = ConfigDict(strict=True, extra="forbid")

    routes: list[SupplierRoute]
    total_quantity: int = Field(gt=0)
    partial: bool
