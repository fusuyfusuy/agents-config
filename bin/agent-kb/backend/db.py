import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from models import ErrorRecord, Solution, RecordInput, SearchResult, ErrorPattern
from kb_engine import KBEngine

DEFAULT_DB_PATH = Path("~/.agent-kb/kb.db").expanduser()

class ErrorDatabase:
    """
    SQLite database interface with error signature hashing, similarity scoring,
    and pattern aggregation.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")

            # 1. Main Errors Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT UNIQUE NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    raw_stack_trace TEXT NOT NULL,
                    normalized_stack_trace TEXT NOT NULL,
                    agent_environment TEXT DEFAULT '{}',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 2. Solutions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS solutions (
                    id TEXT PRIMARY KEY,
                    error_id TEXT NOT NULL,
                    cause TEXT NOT NULL,
                    patch_or_fix TEXT NOT NULL,
                    explanation TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    verification_score REAL DEFAULT 1.0,
                    verified_count INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(error_id) REFERENCES errors(id) ON DELETE CASCADE
                );
            """)

            conn.commit()

        # Auto-seed initial dataset if database was just created / empty
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM errors")
            row = cursor.fetchone()
            if row and row["count"] == 0:
                self._auto_seed()

    def _auto_seed(self):
        try:
            from seed_data import SEED_RECORDS
            for record_in in SEED_RECORDS:
                self.add_record(record_in)
        except Exception:
            pass

    def add_record(self, record_input: RecordInput) -> Tuple[ErrorRecord, Solution]:
        """
        Stores or updates an error record and solution.
        """
        raw_trace = record_input.stack_trace or record_input.error_message
        normalized = KBEngine.normalize_error(raw_trace)
        fingerprint = KBEngine.compute_fingerprint(normalized, record_input.error_type)
        now = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if record with matching fingerprint already exists
            cursor.execute("SELECT id FROM errors WHERE fingerprint = ?", (fingerprint,))
            existing = cursor.fetchone()

            if existing:
                error_id = existing["id"]
                # Update timestamp & tags if provided
                cursor.execute("SELECT tags, agent_environment FROM errors WHERE id = ?", (error_id,))
                row = cursor.fetchone()
                existing_tags = json.loads(row["tags"]) if row["tags"] else []
                merged_tags = list(set(existing_tags + record_input.tags))
                
                cursor.execute("""
                    UPDATE errors
                    SET updated_at = ?, tags = ?
                    WHERE id = ?
                """, (now, json.dumps(merged_tags), error_id))
            else:
                error_id = str(uuid.uuid4())
                env_json = json.dumps(record_input.agent_environment or {})
                tags_json = json.dumps(record_input.tags or [])

                cursor.execute("""
                    INSERT INTO errors (id, fingerprint, error_type, error_message, raw_stack_trace, normalized_stack_trace, agent_environment, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (error_id, fingerprint, record_input.error_type, record_input.error_message, raw_trace, normalized, env_json, tags_json, now, now))

            # Insert new solution
            solution_id = str(uuid.uuid4())
            sol_tags_json = json.dumps(record_input.tags or [])
            cursor.execute("""
                INSERT INTO solutions (id, error_id, cause, patch_or_fix, explanation, tags, verification_score, verified_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (solution_id, error_id, record_input.cause, record_input.patch_or_fix, record_input.explanation or "", sol_tags_json, record_input.verification_score, now))

            conn.commit()

        # Fetch constructed ErrorRecord and Solution
        return self.get_error_record_with_solution(error_id, solution_id)

    def get_error_record_with_solution(self, error_id: str, solution_id: str) -> Tuple[ErrorRecord, Solution]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM errors WHERE id = ?", (error_id,))
            err_row = cursor.fetchone()

            cursor.execute("SELECT * FROM solutions WHERE error_id = ?", (error_id,))
            sol_rows = cursor.fetchall()

            cursor.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
            target_sol_row = cursor.fetchone()

        solutions = [
            Solution(
                id=s["id"],
                cause=s["cause"],
                patch_or_fix=s["patch_or_fix"],
                explanation=s["explanation"],
                tags=json.loads(s["tags"]),
                verification_score=s["verification_score"],
                verified_count=s["verified_count"],
                created_at=s["created_at"]
            )
            for s in sol_rows
        ]

        target_sol = Solution(
            id=target_sol_row["id"],
            cause=target_sol_row["cause"],
            patch_or_fix=target_sol_row["patch_or_fix"],
            explanation=target_sol_row["explanation"],
            tags=json.loads(target_sol_row["tags"]),
            verification_score=target_sol_row["verification_score"],
            verified_count=target_sol_row["verified_count"],
            created_at=target_sol_row["created_at"]
        )

        error_record = ErrorRecord(
            id=err_row["id"],
            fingerprint=err_row["fingerprint"],
            error_type=err_row["error_type"],
            error_message=err_row["error_message"],
            raw_stack_trace=err_row["raw_stack_trace"],
            normalized_stack_trace=err_row["normalized_stack_trace"],
            agent_environment=json.loads(err_row["agent_environment"]),
            tags=json.loads(err_row["tags"]),
            solutions=solutions,
            created_at=err_row["created_at"],
            updated_at=err_row["updated_at"]
        )

        return error_record, target_sol

    def search_solutions(self, query: str, error_type: Optional[str] = None, tags: Optional[List[str]] = None, limit: int = 5, min_score: float = 0.0) -> List[SearchResult]:
        """
        Hybrid search engine:
        1. Exact Fingerprint Match (Score 1.0)
        2. Token/N-gram Similarity Fuzzy Match
        """
        normalized_query = KBEngine.normalize_error(query)
        computed_fp = KBEngine.compute_fingerprint(normalized_query, error_type or "")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Exact Fingerprint Match
            cursor.execute("SELECT id FROM errors WHERE fingerprint = ?", (computed_fp,))
            fp_match = cursor.fetchone()
            if fp_match:
                rec, sol = self._get_full_record(conn, fp_match["id"])
                if rec and sol:
                    return [
                        SearchResult(
                            record=rec,
                            matched_solution=sol,
                            confidence_score=1.0,
                            match_type="fingerprint_exact",
                            explanation="Exact stack trace fingerprint hash match."
                        )
                    ]

            # Also check fingerprint without error_type filter
            computed_fp_no_type = KBEngine.compute_fingerprint(normalized_query, "")
            cursor.execute("SELECT id FROM errors WHERE fingerprint = ?", (computed_fp_no_type,))
            fp_match2 = cursor.fetchone()
            if fp_match2:
                rec, sol = self._get_full_record(conn, fp_match2["id"])
                if rec and sol:
                    return [
                        SearchResult(
                            record=rec,
                            matched_solution=sol,
                            confidence_score=1.0,
                            match_type="fingerprint_exact",
                            explanation="Exact stack trace fingerprint hash match (untyped)."
                        )
                    ]

            # 2. Fetch candidate records from DB
            cursor.execute("SELECT * FROM errors")
            all_err_rows = cursor.fetchall()

        results: List[SearchResult] = []
        for err_row in all_err_rows:
            rec, sol = self._get_full_record_from_row(conn, err_row)
            if not rec or not sol:
                continue

            # Optional error_type filtering
            if error_type and error_type.lower() not in rec.error_type.lower():
                # Allow partial match or penalty
                type_match = False
            else:
                type_match = True

            # Optional tags filtering
            if tags:
                if not any(t.lower() in [rt.lower() for rt in rec.tags] for t in tags):
                    continue

            # Compute hybrid similarity score
            target_text = f"{rec.error_type} {rec.error_message} {rec.normalized_stack_trace} {sol.cause}"
            sim_score = KBEngine.calculate_token_similarity(normalized_query, target_text)

            # Verification score boost (scale 0-5 -> 0-0.2 boost)
            v_boost = min(sol.verification_score / 5.0, 1.0) * 0.15

            # Combined confidence score
            confidence = min(round(sim_score * 0.85 + v_boost, 4), 0.99)
            if not type_match:
                confidence *= 0.8

            if confidence >= min_score and confidence > 0.15:
                match_type = "fts5_keyword" if sim_score > 0.4 else "token_similarity"
                results.append(
                    SearchResult(
                        record=rec,
                        matched_solution=sol,
                        confidence_score=confidence,
                        match_type=match_type,
                        explanation=f"Matched using token cosine similarity ({int(sim_score*100)}%) with verification boost."
                    )
                )

        # Sort by confidence_score descending
        results.sort(key=lambda r: r.confidence_score, reverse=True)
        return results[:limit]

    def _get_full_record(self, conn: sqlite3.Connection, error_id: str) -> Tuple[Optional[ErrorRecord], Optional[Solution]]:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM errors WHERE id = ?", (error_id,))
        err_row = cursor.fetchone()
        if not err_row:
            return None, None
        return self._get_full_record_from_row(conn, err_row)

    def _get_full_record_from_row(self, conn: sqlite3.Connection, err_row: sqlite3.Row) -> Tuple[Optional[ErrorRecord], Optional[Solution]]:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM solutions WHERE error_id = ? ORDER BY verification_score DESC, verified_count DESC", (err_row["id"],))
        sol_rows = cursor.fetchall()
        if not sol_rows:
            return None, None

        solutions = [
            Solution(
                id=s["id"],
                cause=s["cause"],
                patch_or_fix=s["patch_or_fix"],
                explanation=s["explanation"],
                tags=json.loads(s["tags"]),
                verification_score=s["verification_score"],
                verified_count=s["verified_count"],
                created_at=s["created_at"]
            )
            for s in sol_rows
        ]

        best_sol = solutions[0]

        record = ErrorRecord(
            id=err_row["id"],
            fingerprint=err_row["fingerprint"],
            error_type=err_row["error_type"],
            error_message=err_row["error_message"],
            raw_stack_trace=err_row["raw_stack_trace"],
            normalized_stack_trace=err_row["normalized_stack_trace"],
            agent_environment=json.loads(err_row["agent_environment"]),
            tags=json.loads(err_row["tags"]),
            solutions=solutions,
            created_at=err_row["created_at"],
            updated_at=err_row["updated_at"]
        )

        return record, best_sol

    def list_patterns(self, limit: int = 10) -> List[ErrorPattern]:
        """
        Calculates recurring error patterns grouped by tags.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tags, error_type FROM errors")
            err_rows = cursor.fetchall()

            cursor.execute("SELECT tags, verification_score FROM solutions")
            sol_rows = cursor.fetchall()

        tag_counts: Dict[str, int] = {}
        tag_types: Dict[str, set] = {}
        tag_scores: Dict[str, List[float]] = {}

        for row in err_rows:
            tags = json.loads(row["tags"]) if row["tags"] else []
            err_type = row["error_type"]
            for tag in tags:
                tag = tag.strip().lower()
                if not tag:
                    continue
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                if tag not in tag_types:
                    tag_types[tag] = set()
                tag_types[tag].add(err_type)

        for row in sol_rows:
            tags = json.loads(row["tags"]) if row["tags"] else []
            score = row["verification_score"]
            for tag in tags:
                tag = tag.strip().lower()
                if not tag:
                    continue
                if tag not in tag_scores:
                    tag_scores[tag] = []
                tag_scores[tag].append(score)

        patterns: List[ErrorPattern] = []
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

        for tag, count in sorted_tags:
            scores = tag_scores.get(tag, [1.0])
            avg_score = round(sum(scores) / len(scores), 2)
            sample_types = list(tag_types.get(tag, []))[:3]
            patterns.append(
                ErrorPattern(
                    tag=tag,
                    count=count,
                    avg_verification_score=avg_score,
                    sample_error_types=sample_types
                )
            )

        return patterns

    def verify_solution(self, solution_id: str, increment: int = 1) -> Optional[Solution]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
            row = cursor.fetchone()
            if not row:
                return None

            new_count = row["verified_count"] + increment
            # Increment verification score up to max 5.0
            new_score = min(5.0, round(row["verification_score"] + (0.5 * increment), 2))

            cursor.execute("""
                UPDATE solutions
                SET verified_count = ?, verification_score = ?
                WHERE id = ?
            """, (new_count, new_score, solution_id))
            conn.commit()

            cursor.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
            updated_row = cursor.fetchone()

        return Solution(
            id=updated_row["id"],
            cause=updated_row["cause"],
            patch_or_fix=updated_row["patch_or_fix"],
            explanation=updated_row["explanation"],
            tags=json.loads(updated_row["tags"]),
            verification_score=updated_row["verification_score"],
            verified_count=updated_row["verified_count"],
            created_at=updated_row["created_at"]
        )

    def get_all_records(self, limit: int = 50, offset: int = 0) -> List[ErrorRecord]:
        records: List[ErrorRecord] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM errors ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            for r in rows:
                rec, _ = self._get_full_record_from_row(conn, r)
                if rec:
                    records.append(rec)
        return records

    def get_record_by_id(self, record_id: str) -> Optional[ErrorRecord]:
        with self.get_connection() as conn:
            rec, _ = self._get_full_record(conn, record_id)
            return rec

