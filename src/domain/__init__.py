"""Domain layer - core business logic and entities."""

from src.domain.entities.failure import Failure
from src.domain.entities.classification import Classification, FailureCategory, Severity
from src.domain.entities.rca import RCA
from src.domain.entities.evidence import Evidence

__all__ = [
    "Failure",
    "Classification",
    "FailureCategory",
    "Severity",
    "RCA",
    "Evidence",
]
