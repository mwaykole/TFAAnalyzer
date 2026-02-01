"""SQLite storage for analysis history and trends."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from src.utils.logging import get_logger

logger = get_logger(__name__)


class AnalysisStore:
    """Stores analysis results for historical tracking, trends, and feedback."""

    def __init__(self, db_path: Path | str = "tfa_history.db"):
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    test_id TEXT,
                    component TEXT,
                    launch_id TEXT NOT NULL,
                    launch_name TEXT,
                    classification TEXT NOT NULL,
                    confidence REAL,
                    severity TEXT,
                    summary TEXT,
                    root_cause TEXT,
                    recommendation TEXT,
                    model TEXT,
                    provider TEXT,
                    error_signature TEXT,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    posted_to_rp BOOLEAN DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_analyses_test_name ON analyses(test_name);
                CREATE INDEX IF NOT EXISTS idx_analyses_launch_id ON analyses(launch_id);
                CREATE INDEX IF NOT EXISTS idx_analyses_classification ON analyses(classification);
                CREATE INDEX IF NOT EXISTS idx_analyses_component ON analyses(component);
                CREATE INDEX IF NOT EXISTS idx_analyses_analyzed_at ON analyses(analyzed_at);
                
                CREATE TABLE IF NOT EXISTS classification_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id INTEGER REFERENCES analyses(id),
                    original_classification TEXT,
                    corrected_classification TEXT,
                    feedback_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    feedback_by TEXT
                );
            """)
            self._migrate_db(conn)
    
    def _migrate_db(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(analyses)")
        columns = {row[1] for row in cursor.fetchall()}
        if "error_signature" not in columns:
            conn.execute("ALTER TABLE analyses ADD COLUMN error_signature TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_error_signature ON analyses(error_signature)")

    def save_analysis(self, analysis: dict[str, Any], launch_id: str, component: str, model: str,
                      provider: str = "", launch_name: str = "", posted_to_rp: bool = False,
                      error_signature: str = "") -> int:
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO analyses (test_name, test_id, component, launch_id, launch_name,
                    classification, confidence, severity, summary, root_cause,
                    recommendation, model, provider, error_signature, posted_to_rp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analysis.get("test_name", ""), str(analysis.get("test_id", "")), component,
                launch_id, launch_name, analysis.get("classification", "Unknown"),
                analysis.get("confidence", 0.0), analysis.get("severity", "MEDIUM"),
                analysis.get("summary", ""), analysis.get("root_cause", ""),
                analysis.get("recommendation", ""), model, provider,
                error_signature or analysis.get("error_signature", ""), posted_to_rp,
            ))
            return cursor.lastrowid

    def save_batch(self, analyses: list[dict[str, Any]], launch_id: str, component: str,
                   model: str, provider: str = "", launch_name: str = "") -> int:
        with self._conn() as conn:
            conn.executemany("""
                INSERT INTO analyses (test_name, test_id, component, launch_id, launch_name,
                    classification, confidence, severity, summary, root_cause,
                    recommendation, model, provider, error_signature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [(
                a.get("test_name", ""), str(a.get("test_id", "")), component,
                str(a.get("launch_id", launch_id)), launch_name,
                a.get("classification", "Unknown"), a.get("confidence", 0.0),
                a.get("severity", "MEDIUM"), a.get("summary", ""),
                a.get("root_cause", ""), a.get("recommendation", ""),
                model, provider, a.get("error_signature", ""),
            ) for a in analyses])
            return len(analyses)

    def get_classification_summary(self, days: int = 30) -> dict[str, int]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT classification, COUNT(*) as count FROM analyses
                WHERE analyzed_at > datetime('now', ?) GROUP BY classification ORDER BY count DESC
            """, (f'-{days} days',))
            return {row["classification"]: row["count"] for row in cursor.fetchall()}

    def get_classification_trends(self, days: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT DATE(analyzed_at) as date, classification, COUNT(*) as count FROM analyses
                WHERE analyzed_at > datetime('now', ?) GROUP BY DATE(analyzed_at), classification
                ORDER BY date DESC, count DESC
            """, (f'-{days} days',))
            return [dict(row) for row in cursor.fetchall()]

    def get_component_health(self, days: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT component, COUNT(*) as total_failures,
                    SUM(CASE WHEN classification = 'Product Bug' THEN 1 ELSE 0 END) as product_bugs,
                    SUM(CASE WHEN classification = 'Test Automation Issue' THEN 1 ELSE 0 END) as auto_issues,
                    AVG(confidence) as avg_confidence
                FROM analyses WHERE analyzed_at > datetime('now', ?)
                GROUP BY component ORDER BY total_failures DESC
            """, (f'-{days} days',))
            return [dict(row) for row in cursor.fetchall()]

    def get_test_history(self, test_name: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM analyses WHERE test_name LIKE ?
                ORDER BY analyzed_at DESC LIMIT ?
            """, (f'%{test_name}%', limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_flaky_tests(self, days: int = 30, min_occurrences: int = 2) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT test_name, COUNT(*) as total,
                    COUNT(DISTINCT classification) as unique_classifications,
                    GROUP_CONCAT(DISTINCT classification) as classifications
                FROM analyses WHERE analyzed_at > datetime('now', ?)
                GROUP BY test_name HAVING COUNT(*) >= ? AND COUNT(DISTINCT classification) > 1
                ORDER BY total DESC
            """, (f'-{days} days', min_occurrences))
            return [dict(row) for row in cursor.fetchall()]

    def record_feedback(self, analysis_id: int, original_classification: str,
                        corrected_classification: str, feedback_by: str = "") -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO classification_feedback 
                (analysis_id, original_classification, corrected_classification, feedback_by)
                VALUES (?, ?, ?, ?)
            """, (analysis_id, original_classification, corrected_classification, feedback_by))

    def get_recent_analyses(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM analyses ORDER BY analyzed_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as total_analyses, COUNT(DISTINCT launch_id) as unique_launches,
                    COUNT(DISTINCT test_name) as unique_tests, COUNT(DISTINCT component) as unique_components,
                    MIN(analyzed_at) as first_analysis, MAX(analyzed_at) as last_analysis
                FROM analyses
            """)
            row = cursor.fetchone()
            return dict(row) if row else {}

    def get_trends_by_day(self, days: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT DATE(analyzed_at) as date, COUNT(*) as total,
                    SUM(CASE WHEN classification = 'Product Bug' THEN 1 ELSE 0 END) as product_bugs,
                    SUM(CASE WHEN classification = 'Test Automation Issue' THEN 1 ELSE 0 END) as auto_issues,
                    SUM(CASE WHEN classification = 'Infrastructure Issue' THEN 1 ELSE 0 END) as infra_issues
                FROM analyses WHERE analyzed_at > datetime('now', ?)
                GROUP BY DATE(analyzed_at) ORDER BY date DESC
            """, (f'-{days} days',))
            return [dict(row) for row in cursor.fetchall()]

    def get_component_health_score(self, days: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT component, COUNT(*) as total_failures,
                    SUM(CASE WHEN classification = 'Product Bug' THEN 1 ELSE 0 END) as product_bugs,
                    ROUND(100.0 * (1.0 - CAST(SUM(CASE WHEN classification = 'Product Bug' 
                        THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)), 1) as health_score
                FROM analyses WHERE analyzed_at > datetime('now', ?) 
                    AND component IS NOT NULL AND component != ''
                GROUP BY component ORDER BY health_score ASC
            """, (f'-{days} days',))
            return [dict(row) for row in cursor.fetchall()]

    def get_top_offenders(self, days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.execute("""
                SELECT test_name, COUNT(*) as failure_count,
                    GROUP_CONCAT(DISTINCT classification) as classifications,
                    MAX(analyzed_at) as last_failure
                FROM analyses WHERE analyzed_at > datetime('now', ?)
                GROUP BY test_name ORDER BY failure_count DESC LIMIT ?
            """, (f'-{days} days', limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_analysis_by_id(self, analysis_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
            row = cursor.fetchone()
            return dict(row) if row else None


_store: AnalysisStore | None = None


def get_store(db_path: Path | str = "tfa_history.db") -> AnalysisStore:
    global _store
    if _store is None:
        _store = AnalysisStore(db_path=db_path)
    return _store
