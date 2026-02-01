"""Failure embedding store for few-shot learning.

Stores past failure classifications with embeddings for similarity search.
Enables retrieving similar past failures to provide as examples to LLM.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.infrastructure.embeddings.text_embedder import TextEmbedder
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SimilarFailure:
    """A similar past failure with known classification."""
    test_name: str
    error_type: str
    error_message: str
    classification: str
    root_cause: str
    reasoning: str
    confidence: float
    similarity_score: float
    timestamp: str
    
    def to_prompt_example(self) -> str:
        """Format as few-shot example for LLM prompt."""
        return f"""## Similar Past Failure (Similarity: {self.similarity_score:.0%})
**Test:** {self.test_name}
**Error:** {self.error_type}: {self.error_message[:200]}
**Classification:** {self.classification} (Confidence: {self.confidence:.0%})
**Root Cause:** {self.root_cause}
**Reasoning:** {self.reasoning[:300]}
"""


@dataclass
class StoredFailure:
    """A stored failure with embedding."""
    id: str
    test_name: str
    error_type: str
    error_message: str
    stack_trace: str
    classification: str
    root_cause: str
    reasoning: str
    confidence: float
    embedding: list[float]
    timestamp: str
    feedback_corrected: bool = False
    corrected_classification: str = ""


class FailureEmbeddingStore:
    """Vector store for past failure classifications.
    
    Uses SQLite with embedded vectors for similarity search.
    Supports finding similar past failures for few-shot learning.
    """
    
    def __init__(
        self,
        db_path: str | Path = ".tfa_cache/failure_embeddings.db",
        embedder: TextEmbedder | None = None,
    ):
        """Initialize the store.
        
        Args:
            db_path: Path to SQLite database
            embedder: Text embedder (creates default if None)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.embedder = embedder or TextEmbedder(backend="auto")
        self._init_db()
        
        logger.info("failure_store_initialized", 
                    db_path=str(self.db_path),
                    embedder=self.embedder.model_name)
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    id TEXT PRIMARY KEY,
                    test_name TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    stack_trace TEXT,
                    classification TEXT NOT NULL,
                    root_cause TEXT,
                    reasoning TEXT,
                    confidence REAL,
                    embedding BLOB,
                    timestamp TEXT,
                    feedback_corrected INTEGER DEFAULT 0,
                    corrected_classification TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_classification 
                ON failures(classification)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_confidence 
                ON failures(confidence DESC)
            """)
            
            conn.commit()
    
    def _create_failure_text(
        self,
        test_name: str,
        error_type: str,
        error_message: str,
        stack_trace: str = "",
    ) -> str:
        """Create text representation for embedding."""
        parts = [
            f"Test: {test_name}",
            f"Error: {error_type}: {error_message[:300]}",
        ]
        if stack_trace:
            parts.append(f"Stack: {stack_trace[:400]}")
        return "\n".join(parts)
    
    def store(
        self,
        test_id: str,
        test_name: str,
        error_type: str,
        error_message: str,
        classification: str,
        root_cause: str,
        reasoning: str,
        confidence: float,
        stack_trace: str = "",
    ) -> None:
        """Store a classified failure.
        
        Args:
            test_id: Unique test identifier
            test_name: Name of the test
            error_type: Type of error (e.g., TimeoutExpiredError)
            error_message: Error message
            classification: Classification result (e.g., PRODUCT_BUG)
            root_cause: Root cause description
            reasoning: LLM reasoning
            confidence: Confidence score (0-1)
            stack_trace: Optional stack trace
        """
        # Create embedding
        text = self._create_failure_text(test_name, error_type, error_message, stack_trace)
        embedding_result = self.embedder.embed(text)
        
        # Store in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO failures 
                (id, test_name, error_type, error_message, stack_trace,
                 classification, root_cause, reasoning, confidence,
                 embedding, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_id,
                test_name,
                error_type,
                error_message[:1000],
                stack_trace[:2000],
                classification,
                root_cause,
                reasoning,
                confidence,
                json.dumps(embedding_result.embedding),
                datetime.now().isoformat(),
            ))
            conn.commit()
        
        logger.debug("failure_stored", 
                     test_id=test_id[:20],
                     classification=classification)
    
    def find_similar(
        self,
        test_name: str,
        error_type: str,
        error_message: str,
        stack_trace: str = "",
        k: int = 3,
        min_confidence: float = 0.7,
        min_similarity: float = 0.5,
    ) -> list[SimilarFailure]:
        """Find similar past failures.
        
        Args:
            test_name: Name of the test
            error_type: Type of error
            error_message: Error message
            stack_trace: Optional stack trace
            k: Number of similar failures to return
            min_confidence: Minimum confidence of past classification
            min_similarity: Minimum similarity score
            
        Returns:
            List of similar past failures
        """
        # Create embedding for query
        text = self._create_failure_text(test_name, error_type, error_message, stack_trace)
        query_embedding = self.embedder.embed(text).embedding
        
        # Get all stored failures
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, test_name, error_type, error_message, 
                       classification, root_cause, reasoning, confidence,
                       embedding, timestamp
                FROM failures
                WHERE confidence >= ?
                ORDER BY confidence DESC
            """, (min_confidence,))
            
            rows = cursor.fetchall()
        
        if not rows:
            logger.debug("no_stored_failures_found")
            return []
        
        # Calculate similarities
        similarities = []
        for row in rows:
            stored_embedding = json.loads(row[8])
            similarity = TextEmbedder.cosine_similarity(query_embedding, stored_embedding)
            
            if similarity >= min_similarity:
                similarities.append((row, similarity))
        
        # Sort by similarity and take top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_k = similarities[:k]
        
        # Build results
        results = []
        for row, similarity in top_k:
            results.append(SimilarFailure(
                test_name=row[1],
                error_type=row[2] or "",
                error_message=row[3] or "",
                classification=row[4],
                root_cause=row[5] or "",
                reasoning=row[6] or "",
                confidence=row[7],
                similarity_score=similarity,
                timestamp=row[9] or "",
            ))
        
        logger.info("similar_failures_found",
                    query_test=test_name[:30],
                    found=len(results),
                    top_similarity=f"{results[0].similarity_score:.0%}" if results else "N/A")
        
        return results
    
    def record_feedback(
        self,
        test_id: str,
        corrected_classification: str,
    ) -> bool:
        """Record feedback correction for a failure.
        
        Args:
            test_id: ID of the failure to correct
            corrected_classification: Correct classification
            
        Returns:
            True if feedback was recorded
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE failures
                SET feedback_corrected = 1,
                    corrected_classification = ?,
                    confidence = 0.99
                WHERE id = ?
            """, (corrected_classification, test_id))
            
            conn.commit()
            updated = cursor.rowcount > 0
        
        if updated:
            logger.info("feedback_recorded",
                        test_id=test_id[:20],
                        corrected_to=corrected_classification)
        
        return updated
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about stored failures."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN feedback_corrected = 1 THEN 1 END) as corrected,
                    AVG(confidence) as avg_confidence
                FROM failures
            """)
            row = cursor.fetchone()
            
            cursor = conn.execute("""
                SELECT classification, COUNT(*) as count
                FROM failures
                GROUP BY classification
                ORDER BY count DESC
            """)
            by_classification = {r[0]: r[1] for r in cursor.fetchall()}
        
        return {
            "total_failures": row[0],
            "corrected_count": row[1],
            "avg_confidence": row[2] or 0.0,
            "by_classification": by_classification,
        }
    
    def build_few_shot_prompt(
        self,
        test_name: str,
        error_type: str,
        error_message: str,
        stack_trace: str = "",
        k: int = 2,
    ) -> str:
        """Build few-shot prompt section with similar past failures.
        
        Args:
            test_name: Name of the test
            error_type: Type of error
            error_message: Error message
            stack_trace: Optional stack trace
            k: Number of examples to include
            
        Returns:
            Formatted prompt section with examples
        """
        similar = self.find_similar(
            test_name=test_name,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            k=k,
        )
        
        if not similar:
            return ""
        
        sections = [
            "# Similar Past Failures (for reference)",
            "The following are similar failures that were previously classified. "
            "Use these as examples to guide your classification:\n",
        ]
        
        for failure in similar:
            sections.append(failure.to_prompt_example())
        
        sections.append("---\n# New Failure to Classify\n")
        
        return "\n".join(sections)
