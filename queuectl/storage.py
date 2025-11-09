"""Job storage layer using SQLite for persistence."""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager


class JobStorage:
    """Manages persistent job storage using SQLite."""
    
    def __init__(self, db_path: str = "queuectl.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    locked_by TEXT,
                    locked_at TEXT
                )
            """)
            
            # Add retry_at column if it doesn't exist (migration)
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN retry_at TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Initialize default config
            conn.execute("""
                INSERT OR IGNORE INTO config (key, value) VALUES
                ('max_retries', '3'),
                ('backoff_base', '2')
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper transaction handling."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def create_job(self, job_id: str, command: str, max_retries: Optional[int] = None) -> Dict:
        """Create a new job."""
        # Use config default if max_retries not specified
        if max_retries is None:
            max_retries = int(self.get_config("max_retries", "3"))
        
        now = datetime.utcnow().isoformat() + "Z"
        job = {
            "id": job_id,
            "command": command,
            "state": "pending",
            "attempts": 0,
            "max_retries": max_retries,
            "created_at": now,
            "updated_at": now
        }
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO jobs (id, command, state, attempts, max_retries, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job["id"],
                job["command"],
                job["state"],
                job["attempts"],
                job["max_retries"],
                job["created_at"],
                job["updated_at"]
            ))
        
        return job
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get a job by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None
    
    def lock_job(self, job_id: str, worker_id: str) -> bool:
        """Try to lock a pending or failed job for processing. Returns True if locked successfully.
        
        Uses atomic UPDATE with WHERE clause to prevent race conditions.
        Only one worker can successfully lock a job at a time.
        """
        with self._get_connection() as conn:
            now = datetime.utcnow().isoformat() + "Z"
            # Try to lock a pending or failed job atomically
            # The WHERE clause ensures only one worker can lock the job
            cursor = conn.execute("""
                UPDATE jobs 
                SET state = 'processing', 
                    locked_by = ?,
                    locked_at = ?,
                    updated_at = ?,
                    retry_at = NULL
                WHERE id = ? AND (state = 'pending' OR state = 'failed')
            """, (worker_id, now, now, job_id))
            
            return cursor.rowcount > 0
    
    def get_next_pending_job(self, worker_id: str) -> Optional[Dict]:
        """Get and lock the next pending job or failed job ready for retry.
        
        Uses atomic UPDATE with subquery to prevent race conditions.
        Only one worker can successfully lock a job at a time.
        """
        with self._get_connection() as conn:
            now = datetime.utcnow().isoformat() + "Z"
            
            # First, try to atomically lock a failed job ready to retry
            # This UPDATE is atomic and prevents race conditions between workers
            cursor = conn.execute("""
                UPDATE jobs 
                SET state = 'processing',
                    locked_by = ?,
                    locked_at = ?,
                    updated_at = ?,
                    retry_at = NULL
                WHERE id IN (
                    SELECT id FROM jobs
                    WHERE state = 'failed' 
                    AND (retry_at IS NULL OR retry_at <= ?)
                    ORDER BY updated_at ASC 
                    LIMIT 1
                )
                AND state = 'failed'
            """, (worker_id, now, now, now))
            
            if cursor.rowcount > 0:
                # Get the job we just locked
                cursor = conn.execute("""
                    SELECT * FROM jobs 
                    WHERE locked_by = ? AND state = 'processing'
                    ORDER BY locked_at DESC
                    LIMIT 1
                """, (worker_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
            
            # If no failed jobs ready, atomically lock a pending job
            cursor = conn.execute("""
                UPDATE jobs 
                SET state = 'processing',
                    locked_by = ?,
                    locked_at = ?,
                    updated_at = ?,
                    retry_at = NULL
                WHERE id IN (
                    SELECT id FROM jobs
                    WHERE state = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT 1
                )
                AND state = 'pending'
            """, (worker_id, now, now))
            
            if cursor.rowcount > 0:
                # Get the job we just locked
                cursor = conn.execute("""
                    SELECT * FROM jobs 
                    WHERE locked_by = ? AND state = 'processing'
                    ORDER BY locked_at DESC
                    LIMIT 1
                """, (worker_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        
        return None
    
    def update_job_state(self, job_id: str, state: str, attempts: Optional[int] = None, retry_at: Optional[str] = None):
        """Update job state and optionally attempts and retry_at."""
        now = datetime.utcnow().isoformat() + "Z"
        
        with self._get_connection() as conn:
            if attempts is not None and retry_at is not None:
                conn.execute("""
                    UPDATE jobs 
                    SET state = ?, attempts = ?, updated_at = ?, locked_by = NULL, locked_at = NULL, retry_at = ?
                    WHERE id = ?
                """, (state, attempts, now, retry_at, job_id))
            elif attempts is not None:
                conn.execute("""
                    UPDATE jobs 
                    SET state = ?, attempts = ?, updated_at = ?, locked_by = NULL, locked_at = NULL, retry_at = NULL
                    WHERE id = ?
                """, (state, attempts, now, job_id))
            elif retry_at is not None:
                conn.execute("""
                    UPDATE jobs 
                    SET state = ?, updated_at = ?, locked_by = NULL, locked_at = NULL, retry_at = ?
                    WHERE id = ?
                """, (state, now, retry_at, job_id))
            else:
                conn.execute("""
                    UPDATE jobs 
                    SET state = ?, updated_at = ?, locked_by = NULL, locked_at = NULL, retry_at = NULL
                    WHERE id = ?
                """, (state, now, job_id))
    
    def increment_attempts(self, job_id: str) -> int:
        """Increment job attempts and return new count."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE jobs 
                SET attempts = attempts + 1, updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat() + "Z", job_id))
            
            job = self.get_job(job_id)
            return job["attempts"] if job else 0
    
    def list_jobs(self, state: Optional[str] = None) -> List[Dict]:
        """List jobs, optionally filtered by state."""
        with self._get_connection() as conn:
            if state:
                cursor = conn.execute("SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC", (state,))
            else:
                cursor = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_job_stats(self) -> Dict[str, int]:
        """Get statistics about job states."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT state, COUNT(*) as count 
                FROM jobs 
                GROUP BY state
            """)
            
            stats = {row["state"]: row["count"] for row in cursor.fetchall()}
            
            # Ensure all states are present
            for state in ["pending", "processing", "completed", "failed", "dead"]:
                if state not in stats:
                    stats[state] = 0
            
            return stats
    
    def get_config(self, key: str, default: str = None) -> Optional[str]:
        """Get configuration value."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
    
    def set_config(self, key: str, value: str):
        """Set configuration value."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)
            """, (key, value))

