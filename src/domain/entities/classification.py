"""Classification entity and related enums."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    """Failure classification categories.
    
    Open/Closed: New categories can be added without modifying existing code.
    """
    
    PRODUCT_BUG = "Product Bug"
    TEST_AUTOMATION_ISSUE = "Test Automation Issue"
    INFRASTRUCTURE_ISSUE = "Infrastructure Issue"
    INTERMITTENT_FAILURE = "Intermittent Failure"
    TO_INVESTIGATE = "To Investigate"
    
    @classmethod
    def from_string(cls, value: str) -> "FailureCategory":
        """Parse category from string, handling LLM phrasing variations."""
        normalized = value.lower().strip().rstrip(".")
        
        exact = {
            "product bug": cls.PRODUCT_BUG,
            "product_bug": cls.PRODUCT_BUG,
            "pb": cls.PRODUCT_BUG,
            "test automation issue": cls.TEST_AUTOMATION_ISSUE,
            "test_automation_issue": cls.TEST_AUTOMATION_ISSUE,
            "automation bug": cls.TEST_AUTOMATION_ISSUE,
            "automation_bug": cls.TEST_AUTOMATION_ISSUE,
            "ta": cls.TEST_AUTOMATION_ISSUE,
            "infrastructure issue": cls.INFRASTRUCTURE_ISSUE,
            "infrastructure_issue": cls.INFRASTRUCTURE_ISSUE,
            "system issue": cls.INFRASTRUCTURE_ISSUE,
            "system_issue": cls.INFRASTRUCTURE_ISSUE,
            "infra": cls.INFRASTRUCTURE_ISSUE,
            "intermittent failure": cls.INTERMITTENT_FAILURE,
            "intermittent_failure": cls.INTERMITTENT_FAILURE,
            "flaky test": cls.INTERMITTENT_FAILURE,
            "flaky_test": cls.INTERMITTENT_FAILURE,
            "flaky": cls.INTERMITTENT_FAILURE,
        }
        
        if normalized in exact:
            return exact[normalized]
        
        # Substring matching for LLM variations like
        # "Product Bug (API error)", "Test Automation Issue - timeout"
        substring_map = [
            ("product bug", cls.PRODUCT_BUG),
            ("product defect", cls.PRODUCT_BUG),
            ("code defect", cls.PRODUCT_BUG),
            ("software bug", cls.PRODUCT_BUG),
            ("test automation", cls.TEST_AUTOMATION_ISSUE),
            ("automation issue", cls.TEST_AUTOMATION_ISSUE),
            ("test issue", cls.TEST_AUTOMATION_ISSUE),
            ("test code", cls.TEST_AUTOMATION_ISSUE),
            ("test framework", cls.TEST_AUTOMATION_ISSUE),
            ("infrastructure", cls.INFRASTRUCTURE_ISSUE),
            ("environment issue", cls.INFRASTRUCTURE_ISSUE),
            ("cluster issue", cls.INFRASTRUCTURE_ISSUE),
            ("platform issue", cls.INFRASTRUCTURE_ISSUE),
            ("intermittent", cls.INTERMITTENT_FAILURE),
            ("flaky", cls.INTERMITTENT_FAILURE),
            ("race condition", cls.INTERMITTENT_FAILURE),
            ("timing issue", cls.INTERMITTENT_FAILURE),
        ]
        
        for keyword, cat in substring_map:
            if keyword in normalized:
                return cat
        
        return cls.TO_INVESTIGATE
    
    @property
    def defect_type_code(self) -> str:
        """Get ReportPortal defect type code."""
        codes = {
            self.PRODUCT_BUG: "pb001",
            self.TEST_AUTOMATION_ISSUE: "ab001",
            self.INFRASTRUCTURE_ISSUE: "si001",
            self.INTERMITTENT_FAILURE: "si001",
            self.TO_INVESTIGATE: "ti001",
        }
        return codes.get(self, "ti001")
    
    @property
    def icon(self) -> str:
        """Get display icon."""
        icons = {
            self.PRODUCT_BUG: "🐛",
            self.TEST_AUTOMATION_ISSUE: "🔧",
            self.INFRASTRUCTURE_ISSUE: "🌐",
            self.INTERMITTENT_FAILURE: "🔄",
            self.TO_INVESTIGATE: "❓",
        }
        return icons.get(self, "❓")


class Severity(str, Enum):
    """Classification severity levels."""
    
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    
    @property
    def icon(self) -> str:
        """Get display icon."""
        icons = {
            self.LOW: "⚪",
            self.MEDIUM: "🟡",
            self.HIGH: "🟠",
            self.CRITICAL: "🔴",
        }
        return icons.get(self, "⚪")


@dataclass
class Classification:
    """Domain entity representing a classification result.
    
    Single Responsibility: Only holds classification data.
    """
    
    category: FailureCategory
    confidence: float
    severity: Severity
    reasoning: str
    recommendation: str = ""
    matched_patterns: list[str] | None = None
    
    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))
        if isinstance(self.category, str):
            self.category = FailureCategory.from_string(self.category)
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity.upper())
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if classification has high confidence (>90%)."""
        return self.confidence >= 0.9
    
    @property
    def confidence_percent(self) -> int:
        """Get confidence as percentage."""
        return int(self.confidence * 100)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "confidence_percent": self.confidence_percent,
            "severity": self.severity.value,
            "reasoning": self.reasoning,
            "recommendation": self.recommendation,
            "matched_patterns": self.matched_patterns,
            "defect_type_code": self.category.defect_type_code,
        }
