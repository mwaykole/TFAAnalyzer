"""API request schemas using Pydantic."""

from enum import Enum
from pydantic import BaseModel, Field


class VerifyModeEnum(str, Enum):
    """Verification mode options for API."""
    NONE = "none"
    RUN = "run"
    ANALYZE_HISTORY = "analyze-history"


class AnalyzeRequest(BaseModel):
    """Request to analyze test failures."""
    
    launch_id: str = Field(..., description="ReportPortal launch ID")
    component: str = Field(..., description="Component to analyze")
    test_id: str | None = Field(None, description="Specific test ID (optional)")
    push_to_rp: bool = Field(False, description="Push results to ReportPortal")
    use_cache: bool = Field(True, description="Use cached results if available")
    use_llm: bool = Field(True, description="Use LLM for complex cases")
    provider: str = Field("claude-cli", description="LLM provider to use")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "launch_id": "9657",
                    "component": "Model_server",
                    "push_to_rp": False,
                    "use_cache": True,
                    "use_llm": True,
                    "provider": "claude-cli",
                }
            ]
        }
    }


class InvestigateRequest(BaseModel):
    """Request for deep RCA investigation."""
    
    launch_id: str = Field(..., description="ReportPortal launch ID")
    component: str = Field(..., description="Component to investigate")
    test_id: str | None = Field(None, description="Specific test ID (optional)")
    push_to_rp: bool = Field(False, description="Push results to ReportPortal")
    verify_mode: VerifyModeEnum = Field(
        VerifyModeEnum.NONE, 
        description="Verification mode: none, run (execute test), analyze-history (pattern analysis)"
    )
    verify_tests: bool = Field(False, description="Legacy: Re-run tests (use verify_mode instead)")
    provider: str = Field("claude-cli", description="LLM provider to use")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "launch_id": "9657",
                    "component": "Model_server",
                    "push_to_rp": True,
                    "verify_mode": "none",
                    "provider": "claude-cli",
                }
            ]
        }
    }


class FeedbackRequest(BaseModel):
    """Request to record feedback on a classification."""
    
    test_id: str = Field(..., description="Test ID that was analyzed")
    original_classification: str = Field(..., description="Original AI classification")
    corrected_classification: str = Field(..., description="Correct classification")
    feedback_by: str = Field("", description="Who provided the feedback")
    notes: str = Field("", description="Additional notes")
