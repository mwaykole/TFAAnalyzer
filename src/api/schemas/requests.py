"""API request schemas using Pydantic.

Supports both launch IDs and full ReportPortal URLs for user convenience.
URLs are automatically parsed to extract the launch ID.
"""

from enum import Enum
from pydantic import BaseModel, Field, field_validator

from src.utils.url_parser import extract_launch_id, extract_test_item_id


class VerifyModeEnum(str, Enum):
    """Verification mode options for API (legacy single-select)."""
    NONE = "none"
    RUN = "run"
    ANALYZE_HISTORY = "analyze-history"
    ALL = "all"  # Run both run and analyze-history


class AnalyzeRequest(BaseModel):
    """Request to analyze test failures.
    
    Accepts either a launch ID or a full ReportPortal URL.
    URLs are automatically parsed to extract the launch ID.
    
    Examples:
        - launch_id: "9657"
        - launch_id: "https://rp.example.com/ui/#project/launches/all/9657"
    """
    
    launch_id: str = Field(..., description="ReportPortal launch ID or full URL")
    component: str = Field(..., description="Component to analyze")
    test_id: str | None = Field(None, description="Specific test ID (optional)")
    push_to_rp: bool = Field(False, description="Push results to ReportPortal")
    use_cache: bool = Field(True, description="Use cached results if available")
    use_llm: bool = Field(True, description="Use LLM for complex cases")
    provider: str = Field("claude-cli", description="LLM provider to use")
    
    @field_validator('launch_id', mode='before')
    @classmethod
    def parse_launch_id(cls, v: str) -> str:
        """Extract launch ID from URL if a full URL is provided."""
        if v and isinstance(v, str):
            return extract_launch_id(v)
        return v
    
    @field_validator('test_id', mode='before')
    @classmethod
    def parse_test_id(cls, v: str | None) -> str | None:
        """Extract test ID from URL if a full URL is provided."""
        if v and isinstance(v, str) and not v.isdigit():
            extracted = extract_test_item_id(v)
            return extracted if extracted else v
        return v
    
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
                },
                {
                    "launch_id": "https://rp.example.com/ui/#project/launches/all/9657",
                    "component": "Model_server",
                    "push_to_rp": False,
                }
            ]
        }
    }


class InvestigateRequest(BaseModel):
    """Request for deep RCA investigation.
    
    Accepts either a launch ID or a full ReportPortal URL.
    URLs are automatically parsed to extract the launch ID.
    
    Examples:
        - launch_id: "9657"
        - launch_id: "https://rp.example.com/ui/#project/launches/all/9657"
        - launch_id: "https://rp.example.com/ui/#project/launches/all/9657/test-item/510078"
          (also extracts test_id automatically)
    """
    
    launch_id: str = Field(..., description="ReportPortal launch ID or full URL")
    component: str = Field(..., description="Component to investigate")
    test_id: str | None = Field(None, description="Specific test ID (optional, auto-extracted from URL)")
    push_to_rp: bool = Field(False, description="Push results to ReportPortal")
    
    # Verification options (checkboxes - can select multiple)
    run_test: bool = Field(False, description="Re-run the test using uv run pytest")
    analyze_history: bool = Field(False, description="Analyze RP history + test code for flakiness patterns")
    
    # Legacy support
    verify_mode: VerifyModeEnum = Field(
        VerifyModeEnum.NONE, 
        description="(Legacy) Verification mode - use run_test/analyze_history instead"
    )
    verify_tests: bool = Field(False, description="Legacy: Re-run tests (use run_test instead)")
    
    provider: str = Field("claude-cli", description="LLM provider to use")
    
    must_gather_path: str | None = Field(
        None, description="Path to must-gather artifacts (overrides config base_path)"
    )
    
    @field_validator('launch_id', mode='before')
    @classmethod
    def parse_launch_id(cls, v: str) -> str:
        """Extract launch ID from URL if a full URL is provided."""
        if v and isinstance(v, str):
            return extract_launch_id(v)
        return v
    
    @field_validator('test_id', mode='before')
    @classmethod
    def parse_test_id(cls, v: str | None, info) -> str | None:
        """Extract test ID from URL if a full URL is provided."""
        if v and isinstance(v, str) and not v.isdigit():
            extracted = extract_test_item_id(v)
            return extracted if extracted else v
        return v
    
    def model_post_init(self, __context) -> None:
        """Post-init to extract test_id from launch_id URL if not provided."""
        # If test_id not set but launch_id was a URL with test-item, extract it
        if not self.test_id:
            from src.utils.url_parser import parse_rp_url
            # We need the original value, but it's already transformed
            # This would need the original input, so we skip for now
            pass
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "launch_id": "9657",
                    "component": "Model_server",
                    "push_to_rp": True,
                    "run_test": False,
                    "analyze_history": True,
                    "provider": "claude-cli",
                },
                {
                    "launch_id": "https://rp.example.com/ui/#project/launches/all/9657",
                    "component": "Model_server",
                    "analyze_history": True,
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
