"""Pydantic models for ReportPortal entities."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field


def coerce_to_str(v: Any) -> str:
    """Coerce value to string (handles int IDs from RP 5.x)."""
    return str(v) if v is not None else ""


StrOrInt = Annotated[str, BeforeValidator(coerce_to_str)]


class TestStatus(str, Enum):
    """Test item status values."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"


class LaunchStatus(str, Enum):
    """Launch status values."""

    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    INTERRUPTED = "INTERRUPTED"


class LogLevel(str, Enum):
    """Log entry level values."""

    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"
    FATAL = "FATAL"


class FailureClassification(str, Enum):
    """Classification categories for test failures."""

    APPLICATION_BUG = "Application Bug"
    TEST_BUG = "Test Bug"
    FLAKY = "Flaky"
    ENVIRONMENT = "Environment"
    DATA_ISSUE = "Data Issue"


class Launch(BaseModel):
    """ReportPortal launch entity."""

    id: StrOrInt = Field(..., description="Launch ID")
    uuid: str | None = Field(default=None, description="Launch UUID")
    name: str = Field(..., description="Launch name")
    number: int = Field(..., description="Launch number")
    status: LaunchStatus = Field(..., description="Launch status")
    start_time: datetime | None = Field(default=None, alias="startTime", description="Launch start time")
    end_time: datetime | None = Field(default=None, alias="endTime", description="Launch end time")
    description: str | None = Field(default=None, description="Launch description")
    attributes: list[dict[str, str]] = Field(
        default_factory=list, description="Launch attributes"
    )
    statistics: dict[str, Any] = Field(
        default_factory=dict, description="Launch statistics"
    )

    class Config:
        use_enum_values = True
        populate_by_name = True


class TestItem(BaseModel):
    """ReportPortal test item entity."""

    id: StrOrInt = Field(..., description="Test item ID")
    uuid: str | None = Field(default=None, description="Test item UUID")
    name: str = Field(..., description="Test item name")
    type: str = Field(..., description="Test item type (STEP, TEST, SUITE, etc.)")
    status: str = Field(..., description="Test status")  # Flexible to handle various status values
    launch_id: StrOrInt = Field(..., alias="launchId", description="Parent launch ID")
    parent_id: StrOrInt | None = Field(default=None, alias="parentId", description="Parent item ID")
    path_names: dict[str, Any] | None = Field(
        default=None, alias="pathNames", description="Path to test item"
    )
    start_time: datetime | None = Field(default=None, alias="startTime", description="Start time")
    end_time: datetime | None = Field(default=None, alias="endTime", description="End time")
    description: str | None = Field(default=None, description="Test description")
    attributes: list[dict[str, str]] = Field(
        default_factory=list, description="Test attributes"
    )
    issue: dict[str, Any] | None = Field(default=None, description="Linked issue")
    has_logs: bool = Field(default=False, alias="hasLogs", description="Whether item has logs")
    has_stats: bool = Field(default=False, alias="hasStats", description="Whether item has stats")

    class Config:
        use_enum_values = True
        populate_by_name = True


class LogEntry(BaseModel):
    """ReportPortal log entry."""

    id: StrOrInt = Field(..., description="Log entry ID")
    uuid: str | None = Field(default=None, description="Log entry UUID")
    item_id: StrOrInt = Field(..., alias="itemId", description="Parent test item ID")
    launch_id: StrOrInt = Field(default="", alias="launchId", description="Parent launch ID")
    time: datetime | None = Field(default=None, alias="logTime", description="Log timestamp")
    level: LogLevel = Field(default=LogLevel.INFO, description="Log level")
    message: str = Field(default="", description="Log message content")
    binary_content: dict[str, Any] | None = Field(
        default=None, alias="binaryContent", description="Binary content metadata"
    )

    class Config:
        use_enum_values = True
        populate_by_name = True


class AnalysisResult(BaseModel):
    """Result of LLM analysis for a test failure."""

    summary: str = Field(..., description="Brief failure summary")
    root_cause: str = Field(..., description="Detailed root cause analysis")
    classification: FailureClassification = Field(
        ..., description="Failure classification"
    )
    recommendation: str = Field(..., description="Recommended fix")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)"
    )

    class Config:
        use_enum_values = True

    def to_comment_markdown(self) -> str:
        """Format analysis result as markdown comment for ReportPortal."""
        confidence_pct = int(self.confidence * 100)
        return f"""## 🤖 AI Analysis

**Classification:** {self.classification}
**Confidence:** {confidence_pct}%

### Summary
{self.summary}

### Root Cause
{self.root_cause}

### Recommendation
{self.recommendation}

---
*Generated by ReportPortal Test Failure Analyzer*"""


class PagedResponse(BaseModel):
    """Paged response from ReportPortal API."""

    content: list[dict[str, Any]] = Field(default_factory=list)
    page: dict[str, int] = Field(default_factory=dict)

    @property
    def total_elements(self) -> int:
        return self.page.get("totalElements", 0)

    @property
    def total_pages(self) -> int:
        return self.page.get("totalPages", 0)

    @property
    def current_page(self) -> int:
        return self.page.get("number", 0)

    @property
    def page_size(self) -> int:
        return self.page.get("size", 0)

