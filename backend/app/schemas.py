from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    security = "security"
    performance = "performance"
    design = "design"
    tech_debt = "tech_debt"
    style = "style"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


# ---- Requests -------------------------------------------------------------

class ReviewRequest(BaseModel):
    """Review either a full source file (`code`) or a unified `diff`."""

    code: str | None = Field(default=None, description="Full source code to review")
    diff: str | None = Field(default=None, description="Unified diff to review")
    filename: str | None = Field(default=None, description="Path/name, used to infer language")
    language: str | None = Field(default=None, description="Override language detection")


class DocRequest(BaseModel):
    code: str = Field(description="Source code to document")
    filename: str | None = None
    language: str | None = None
    style: str = Field(default="reference", description="reference | readme | tutorial")


# ---- Responses ------------------------------------------------------------

class FindingOut(BaseModel):
    category: Category
    severity: Severity
    title: str
    detail: str
    suggestion: str | None = None
    file_path: str | None = None
    line: int | None = None
    origin: str = "heuristic"

    model_config = {"from_attributes": True}


class ReviewOut(BaseModel):
    id: int
    created_at: datetime
    source: str
    language: str | None
    engine: str
    summary: str | None
    tech_debt_score: float | None
    repo: str | None = None
    pr_number: int | None = None
    findings: list[FindingOut]

    model_config = {"from_attributes": True}


class ReviewSummary(BaseModel):
    """Lightweight list item (no findings body)."""

    id: int
    created_at: datetime
    source: str
    engine: str
    language: str | None
    tech_debt_score: float | None
    finding_count: int


class DocResponse(BaseModel):
    language: str | None
    engine: str
    documentation: str
