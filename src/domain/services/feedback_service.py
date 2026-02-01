"""Feedback learning service for improving classification accuracy.

Collects user corrections and uses them to:
1. Update the embedding store with corrected classifications
2. Detect patterns that should become quick rules
3. Track accuracy metrics over time
4. Generate improvement suggestions
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import defaultdict

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FeedbackEntry:
    """A single feedback correction."""
    id: str
    test_id: str
    test_name: str
    error_pattern: str
    original_classification: str
    corrected_classification: str
    original_confidence: float
    feedback_by: str
    notes: str
    timestamp: str
    applied: bool = False


@dataclass
class AccuracyMetrics:
    """Accuracy metrics over time."""
    total_classifications: int
    total_corrections: int
    accuracy_rate: float
    by_category: dict[str, dict[str, int]]  # category -> {correct, incorrect}
    common_mistakes: list[dict[str, Any]]  # Most frequent misclassifications
    improvement_trend: list[dict[str, Any]]  # Weekly accuracy


@dataclass
class SuggestedRule:
    """A suggested quick rule based on feedback patterns."""
    pattern: str
    suggested_classification: str
    confidence: float
    occurrences: int
    example_tests: list[str]
    reason: str


class FeedbackService:
    """Service for collecting and learning from user feedback.
    
    Features:
    - Record classification corrections
    - Update embedding store with corrections
    - Detect patterns for new quick rules
    - Track accuracy metrics
    """
    
    def __init__(
        self,
        db_path: str | Path = ".tfa_cache/feedback.db",
        embedding_store: Any = None,
    ):
        """Initialize the feedback service.
        
        Args:
            db_path: Path to SQLite database for feedback storage
            embedding_store: Optional FailureEmbeddingStore for updating
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_store = embedding_store
        self._init_db()
        
        logger.info("feedback_service_initialized", db_path=str(self.db_path))
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL,
                    test_name TEXT,
                    error_pattern TEXT,
                    original_classification TEXT NOT NULL,
                    corrected_classification TEXT NOT NULL,
                    original_confidence REAL,
                    feedback_by TEXT,
                    notes TEXT,
                    timestamp TEXT,
                    applied INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_original 
                ON feedback(original_classification)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corrected 
                ON feedback(corrected_classification)
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suggested_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    confidence REAL,
                    occurrences INTEGER,
                    example_tests TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT
                )
            """)
            
            conn.commit()
    
    def record_feedback(
        self,
        test_id: str,
        original_classification: str,
        corrected_classification: str,
        test_name: str = "",
        error_pattern: str = "",
        original_confidence: float = 0.0,
        feedback_by: str = "",
        notes: str = "",
    ) -> FeedbackEntry:
        """Record a classification correction.
        
        Args:
            test_id: ID of the test that was misclassified
            original_classification: The AI's original classification
            corrected_classification: The correct classification
            test_name: Name of the test
            error_pattern: Error pattern from the failure
            original_confidence: Original confidence score
            feedback_by: Who provided the feedback
            notes: Additional notes
            
        Returns:
            FeedbackEntry record
        """
        import uuid
        
        feedback_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        
        entry = FeedbackEntry(
            id=feedback_id,
            test_id=test_id,
            test_name=test_name,
            error_pattern=error_pattern,
            original_classification=original_classification,
            corrected_classification=corrected_classification,
            original_confidence=original_confidence,
            feedback_by=feedback_by,
            notes=notes,
            timestamp=timestamp,
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feedback 
                (id, test_id, test_name, error_pattern, original_classification,
                 corrected_classification, original_confidence, feedback_by, notes, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.test_id,
                entry.test_name,
                entry.error_pattern,
                entry.original_classification,
                entry.corrected_classification,
                entry.original_confidence,
                entry.feedback_by,
                entry.notes,
                entry.timestamp,
            ))
            conn.commit()
        
        logger.info("feedback_recorded",
                    test_id=test_id[:20],
                    original=original_classification,
                    corrected=corrected_classification)
        
        # Update embedding store if available
        if self.embedding_store:
            try:
                self.embedding_store.record_feedback(
                    test_id=test_id,
                    corrected_classification=corrected_classification,
                )
            except Exception as e:
                logger.warning("embedding_update_failed", error=str(e))
        
        # Check for pattern emergence
        self._check_for_new_patterns(error_pattern, corrected_classification)
        
        return entry
    
    def get_accuracy_metrics(self, days: int = 30) -> AccuracyMetrics:
        """Calculate accuracy metrics from feedback.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            AccuracyMetrics with detailed stats
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total counts
            cursor = conn.execute("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN original_classification = corrected_classification THEN 1 END) as correct
                FROM feedback
                WHERE timestamp >= datetime('now', ?)
            """, (f"-{days} days",))
            row = cursor.fetchone()
            total = row[0]
            correct = row[1]
            
            # By category breakdown
            cursor = conn.execute("""
                SELECT original_classification, corrected_classification, COUNT(*) as count
                FROM feedback
                WHERE timestamp >= datetime('now', ?)
                GROUP BY original_classification, corrected_classification
            """, (f"-{days} days",))
            
            by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "incorrect": 0})
            common_mistakes: list[dict] = []
            
            for orig, corr, count in cursor.fetchall():
                if orig == corr:
                    by_category[orig]["correct"] += count
                else:
                    by_category[orig]["incorrect"] += count
                    common_mistakes.append({
                        "from": orig,
                        "to": corr,
                        "count": count,
                    })
            
            # Sort mistakes by frequency
            common_mistakes.sort(key=lambda x: x["count"], reverse=True)
            
            # Weekly trend
            cursor = conn.execute("""
                SELECT 
                    strftime('%Y-%W', timestamp) as week,
                    COUNT(*) as total,
                    SUM(CASE WHEN original_classification = corrected_classification THEN 1 ELSE 0 END) as correct
                FROM feedback
                WHERE timestamp >= datetime('now', ?)
                GROUP BY week
                ORDER BY week
            """, (f"-{days} days",))
            
            improvement_trend = [
                {
                    "week": row[0],
                    "total": row[1],
                    "correct": row[2],
                    "accuracy": row[2] / row[1] if row[1] > 0 else 0,
                }
                for row in cursor.fetchall()
            ]
        
        return AccuracyMetrics(
            total_classifications=total,
            total_corrections=total - correct,
            accuracy_rate=correct / total if total > 0 else 1.0,
            by_category=dict(by_category),
            common_mistakes=common_mistakes[:10],
            improvement_trend=improvement_trend,
        )
    
    def _check_for_new_patterns(
        self,
        error_pattern: str,
        classification: str,
    ) -> None:
        """Check if a pattern appears frequently enough to become a rule.
        
        Args:
            error_pattern: The error pattern
            classification: The corrected classification
        """
        if not error_pattern or len(error_pattern) < 10:
            return
        
        # Normalize pattern
        pattern_key = error_pattern[:100].lower()
        
        with sqlite3.connect(self.db_path) as conn:
            # Count occurrences of this pattern with this classification
            cursor = conn.execute("""
                SELECT COUNT(*), GROUP_CONCAT(test_name, '|||')
                FROM feedback
                WHERE error_pattern LIKE ? 
                AND corrected_classification = ?
            """, (f"%{pattern_key[:50]}%", classification))
            
            row = cursor.fetchone()
            count = row[0]
            examples = (row[1] or "").split("|||")[:3]
            
            # If pattern appears 3+ times with same correction, suggest a rule
            if count >= 3:
                # Check if we already have this suggestion
                cursor = conn.execute("""
                    SELECT id FROM suggested_rules
                    WHERE pattern LIKE ? AND classification = ?
                """, (f"%{pattern_key[:30]}%", classification))
                
                if not cursor.fetchone():
                    conn.execute("""
                        INSERT INTO suggested_rules
                        (pattern, classification, confidence, occurrences, example_tests, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        pattern_key[:100],
                        classification,
                        min(0.9, 0.7 + 0.05 * count),
                        count,
                        json.dumps(examples),
                        datetime.now().isoformat(),
                    ))
                    conn.commit()
                    
                    logger.info("new_rule_suggested",
                                pattern=pattern_key[:30],
                                classification=classification,
                                occurrences=count)
    
    def get_suggested_rules(self, min_occurrences: int = 3) -> list[SuggestedRule]:
        """Get suggested quick rules based on feedback patterns.
        
        Args:
            min_occurrences: Minimum pattern occurrences
            
        Returns:
            List of suggested rules
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT pattern, classification, confidence, occurrences, example_tests
                FROM suggested_rules
                WHERE status = 'pending' AND occurrences >= ?
                ORDER BY occurrences DESC
            """, (min_occurrences,))
            
            rules = []
            for row in cursor.fetchall():
                rules.append(SuggestedRule(
                    pattern=row[0],
                    suggested_classification=row[1],
                    confidence=row[2],
                    occurrences=row[3],
                    example_tests=json.loads(row[4] or "[]"),
                    reason=f"Pattern occurred {row[3]} times with same correction",
                ))
            
            return rules
    
    def apply_suggested_rule(self, pattern: str) -> bool:
        """Mark a suggested rule as applied.
        
        Args:
            pattern: The pattern to mark as applied
            
        Returns:
            True if updated
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE suggested_rules
                SET status = 'applied'
                WHERE pattern LIKE ?
            """, (f"%{pattern[:30]}%",))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_feedback_for_test(self, test_id: str) -> list[FeedbackEntry]:
        """Get all feedback for a specific test.
        
        Args:
            test_id: The test ID
            
        Returns:
            List of feedback entries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, test_id, test_name, error_pattern, original_classification,
                       corrected_classification, original_confidence, feedback_by, notes,
                       timestamp, applied
                FROM feedback
                WHERE test_id = ?
                ORDER BY timestamp DESC
            """, (test_id,))
            
            entries = []
            for row in cursor.fetchall():
                entries.append(FeedbackEntry(
                    id=row[0],
                    test_id=row[1],
                    test_name=row[2] or "",
                    error_pattern=row[3] or "",
                    original_classification=row[4],
                    corrected_classification=row[5],
                    original_confidence=row[6] or 0.0,
                    feedback_by=row[7] or "",
                    notes=row[8] or "",
                    timestamp=row[9] or "",
                    applied=bool(row[10]),
                ))
            
            return entries
    
    def export_rules_yaml(self) -> str:
        """Export suggested rules as YAML for knowledge_base.yaml.
        
        Returns:
            YAML-formatted string for quick_rules section
        """
        rules = self.get_suggested_rules(min_occurrences=3)
        
        if not rules:
            return "# No suggested rules from feedback yet"
        
        lines = [
            "# ========================================",
            "# Auto-generated rules from feedback",
            "# ========================================",
            "",
        ]
        
        for rule in rules:
            # Clean up pattern for regex
            pattern = rule.pattern.replace(".", r"\.")
            pattern = pattern.replace("(", r"\(").replace(")", r"\)")
            
            lines.extend([
                f"  - name: \"Feedback: {rule.suggested_classification.lower()}\"",
                f"    pattern: \"{pattern}\"",
                f"    classification: \"{rule.suggested_classification.lower()}\"",
                f"    reason: \"Learned from {rule.occurrences} user corrections\"",
                f"    severity: \"medium\"",
                "",
            ])
        
        return "\n".join(lines)
