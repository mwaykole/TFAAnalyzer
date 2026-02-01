"""API response schemas using Pydantic."""

from pydantic import BaseModel, Field
from typing import Literal


class ClassificationDetails(BaseModel):
    """Classification details in response."""
    
    category: str = Field(..., description="Classification category")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    confidence_percent: int = Field(..., ge=0, le=100, description="Confidence as percentage")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(..., description="Severity level")


class AnalysisResult(BaseModel):
    """Single analysis result."""
    
    test_name: str = Field(..., description="Name of the test")
    test_id: str = Field(..., description="Test item ID")
    classification: ClassificationDetails
    root_cause: str = Field(..., description="Root cause description")
    reasoning: str = Field(..., description="Classification reasoning")
    recommendation: str = Field(..., description="Recommended action")
    cached: bool = Field(False, description="Result was from cache")
    from_rp: bool = Field(False, description="Result was from existing RP classification")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "test_name": "test_model_deployment",
                    "test_id": "12345",
                    "classification": {
                        "category": "Product Bug",
                        "confidence": 0.85,
                        "confidence_percent": 85,
                        "severity": "HIGH",
                    },
                    "root_cause": "InferenceService failed to reach Ready state",
                    "reasoning": "Server returned 503 errors consistently",
                    "recommendation": "Check service logs and resource limits",
                    "cached": False,
                    "from_rp": False,
                }
            ]
        }
    }


class AnalyzeResponse(BaseModel):
    """Response from analyze endpoint."""
    
    launch_id: str
    component: str
    total_failures: int
    results: list[AnalysisResult]
    summary: dict[str, int] = Field(default_factory=dict, description="Count by classification")


class VerificationDetailsSchema(BaseModel):
    """Verification result details."""
    
    mode: str = Field("none", description="Verification mode: none, run, analyze-history")
    status: str = Field("not_run", description="Verification status")
    output: str = Field("", description="Verification output (truncated)")
    confidence: float = Field(0.0, description="Confidence from verification")
    reason: str = Field("", description="Reason for the verification result")
    is_intermittent: bool = Field(False, description="Whether test is intermittent")
    details: dict = Field(default_factory=dict, description="Additional verification details")


class TimeoutAnalysisSchema(BaseModel):
    """Timeout analysis details."""
    
    operation_type: str = Field("", description="Type of operation that timed out")
    timeout_used: int = Field(0, description="Timeout value used (seconds)")
    expected_min: int = Field(0, description="Expected minimum timeout")
    expected_max: int = Field(0, description="Expected maximum timeout")
    verdict: str = Field("", description="Verdict: too_short, within_range, too_long")
    recommendation: str = Field("", description="Recommendation based on analysis")


class ClusterInfoSchema(BaseModel):
    """Cluster/systemic issue information."""
    
    cluster_id: str = Field("", description="Cluster identifier")
    likely_root_cause: str = Field("", description="Likely root cause")
    category: str = Field("", description="Issue category")
    recommendation: str = Field("", description="Recommendation")
    affected_tests: int = Field(0, description="Number of affected tests")


class InvestigationResult(BaseModel):
    """Single investigation result with enhanced analysis."""
    
    test_name: str = Field(..., description="Name of the test")
    test_id: str = Field(..., description="Test item ID")
    classification: ClassificationDetails
    root_cause: str
    reasoning: str
    evidence_summary: str = Field(..., description="Summary of evidence used")
    recommendation: str
    verified: bool = Field(False, description="Whether verification was performed")
    verification_result: str = Field("not_run", description="Verification status")
    verification_details: VerificationDetailsSchema | None = Field(None, description="Full verification details")
    
    # Code fetcher fields
    github_url: str = Field("", description="GitHub URL to test source")
    test_file: str = Field("", description="Test file path")
    code_analysis: str = Field("", description="Code analysis summary")
    fixtures: list[str] = Field(default_factory=list, description="Test fixtures used")
    
    # Enhanced analysis fields
    timeout_analysis: TimeoutAnalysisSchema | None = Field(None, description="Timeout analysis if applicable")
    cluster_info: ClusterInfoSchema | None = Field(None, description="Systemic issue info if detected")
    calibrated_confidence: float | None = Field(None, description="Calibrated confidence score")
    confidence_explanation: str | None = Field(None, description="Confidence calibration explanation")


class InvestigateResponse(BaseModel):
    """Response from investigate endpoint."""
    
    launch_id: str
    component: str
    total_failures: int
    results: list[InvestigationResult]
    summary: dict[str, int]


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str = "2.0.0"
    cache_available: bool
    rp_configured: bool
    llm_providers: list[str]
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "version": "2.0.0",
                    "cache_available": True,
                    "rp_configured": True,
                    "llm_providers": ["claude-cli", "anthropic", "groq", "ollama"],
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")
