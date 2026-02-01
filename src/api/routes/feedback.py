"""Feedback API routes for recording corrections and viewing metrics."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from src.domain.services.feedback_service import FeedbackService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Initialize feedback service
_feedback_service: FeedbackService | None = None


def get_feedback_service() -> FeedbackService:
    """Get or create feedback service singleton."""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackService()
    return _feedback_service


class FeedbackRequest(BaseModel):
    """Request to record classification feedback."""
    
    test_id: str = Field(..., description="ID of the test that was classified")
    original_classification: str = Field(..., description="Original AI classification")
    corrected_classification: str = Field(..., description="Correct classification")
    test_name: str = Field("", description="Name of the test")
    error_pattern: str = Field("", description="Error pattern for learning")
    original_confidence: float = Field(0.0, description="Original confidence score")
    feedback_by: str = Field("", description="Who provided the feedback")
    notes: str = Field("", description="Additional notes")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "test_id": "test_123",
                    "original_classification": "PRODUCT_BUG",
                    "corrected_classification": "INFRASTRUCTURE",
                    "test_name": "test_model_serving",
                    "error_pattern": "TimeoutExpiredError",
                    "feedback_by": "engineer@example.com",
                    "notes": "This was a cluster resource issue",
                }
            ]
        }
    }


class FeedbackResponse(BaseModel):
    """Response after recording feedback."""
    
    success: bool
    feedback_id: str
    message: str


class AccuracyResponse(BaseModel):
    """Accuracy metrics response."""
    
    total_classifications: int
    total_corrections: int
    accuracy_rate: float
    by_category: dict[str, dict[str, int]]
    common_mistakes: list[dict[str, Any]]
    improvement_trend: list[dict[str, Any]]


class SuggestedRulesResponse(BaseModel):
    """Suggested rules response."""
    
    rules: list[dict[str, Any]]
    yaml_export: str


@router.post("/feedback", response_model=FeedbackResponse)
async def record_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Record a classification correction.
    
    Use this endpoint when the AI classification was incorrect.
    The system will learn from this feedback to improve accuracy.
    """
    logger.info("feedback_received",
                test_id=request.test_id,
                original=request.original_classification,
                corrected=request.corrected_classification)
    
    try:
        service = get_feedback_service()
        entry = service.record_feedback(
            test_id=request.test_id,
            original_classification=request.original_classification,
            corrected_classification=request.corrected_classification,
            test_name=request.test_name,
            error_pattern=request.error_pattern,
            original_confidence=request.original_confidence,
            feedback_by=request.feedback_by,
            notes=request.notes,
        )
        
        return FeedbackResponse(
            success=True,
            feedback_id=entry.id,
            message=f"Feedback recorded. Classification updated from {request.original_classification} to {request.corrected_classification}",
        )
    except Exception as e:
        logger.error("feedback_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/metrics", response_model=AccuracyResponse)
async def get_accuracy_metrics(days: int = 30) -> AccuracyResponse:
    """Get accuracy metrics from feedback data.
    
    Shows:
    - Overall accuracy rate
    - Breakdown by category
    - Common misclassifications
    - Improvement trend over time
    """
    try:
        service = get_feedback_service()
        metrics = service.get_accuracy_metrics(days=days)
        
        return AccuracyResponse(
            total_classifications=metrics.total_classifications,
            total_corrections=metrics.total_corrections,
            accuracy_rate=metrics.accuracy_rate,
            by_category=metrics.by_category,
            common_mistakes=metrics.common_mistakes,
            improvement_trend=metrics.improvement_trend,
        )
    except Exception as e:
        logger.error("metrics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/suggested-rules", response_model=SuggestedRulesResponse)
async def get_suggested_rules(min_occurrences: int = 3) -> SuggestedRulesResponse:
    """Get suggested quick rules based on feedback patterns.
    
    When multiple feedbacks show the same correction pattern,
    the system suggests adding it as a quick rule.
    """
    try:
        service = get_feedback_service()
        rules = service.get_suggested_rules(min_occurrences=min_occurrences)
        
        rules_list = [
            {
                "pattern": r.pattern,
                "classification": r.suggested_classification,
                "confidence": r.confidence,
                "occurrences": r.occurrences,
                "example_tests": r.example_tests,
                "reason": r.reason,
            }
            for r in rules
        ]
        
        yaml_export = service.export_rules_yaml()
        
        return SuggestedRulesResponse(
            rules=rules_list,
            yaml_export=yaml_export,
        )
    except Exception as e:
        logger.error("suggested_rules_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback/apply-rule")
async def apply_suggested_rule(pattern: str) -> dict[str, bool]:
    """Mark a suggested rule as applied.
    
    Call this after adding a suggested rule to knowledge_base.yaml.
    """
    try:
        service = get_feedback_service()
        success = service.apply_suggested_rule(pattern)
        return {"success": success}
    except Exception as e:
        logger.error("apply_rule_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
