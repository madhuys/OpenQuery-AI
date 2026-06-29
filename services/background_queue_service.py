"""
Background Queue Service for handling slow PDF processing.

This service manages a SQLite-based queue for PDFs that timeout during fast lane processing.
PDFs in the queue are processed by a background worker without time limits.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import json
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class BackgroundQueueService:
    """Manages the background processing queue for slow PDFs and HTML."""

    def __init__(self, db_path: str = "db/background_queue.db"):
        """
        Initialize the background queue service.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Create the background queue table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS background_pdf_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    doc_type TEXT DEFAULT 'pdf',
                    status TEXT DEFAULT 'pending',
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    result_cache_key TEXT,
                    metadata TEXT
                )
            """)

            # Create index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url ON background_pdf_queue(url)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON background_pdf_queue(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_type ON background_pdf_queue(doc_type)
            """)

            conn.commit()
            logger.info(f"Background queue database initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_to_queue(
        self,
        url: str,
        doc_type: str = 'pdf',
        metadata: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> bool:
        """
        Add a URL to the background processing queue.

        Args:
            url: URL to process (PDF or HTML)
            doc_type: Type of document ('pdf' or 'html')
            metadata: Optional metadata about the document
            max_retries: Maximum retry attempts

        Returns:
            True if added successfully, False if already exists
        """
        try:
            with self._get_connection() as conn:
                metadata_json = json.dumps(metadata) if metadata else None

                conn.execute("""
                    INSERT OR IGNORE INTO background_pdf_queue
                    (url, doc_type, status, metadata, max_retries)
                    VALUES (?, ?, 'pending', ?, ?)
                """, (url, doc_type, metadata_json, max_retries))

                conn.commit()

                # Check if actually inserted
                cursor = conn.execute(
                    "SELECT id FROM background_pdf_queue WHERE url = ?",
                    (url,)
                )
                result = cursor.fetchone()

                if result:
                    logger.info(f"Added {doc_type.upper()} to background queue: {url}")
                    return True
                else:
                    logger.debug(f"{doc_type.upper()} already in queue: {url}")
                    return False

        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return False

    def get_next_pending(self) -> Optional[Dict[str, Any]]:
        """
        Get the next pending item from the queue (FIFO).

        Returns:
            Dictionary with queue item details or None if queue is empty
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM background_pdf_queue
                    WHERE status = 'pending'
                    AND retry_count < max_retries
                    ORDER BY added_at ASC
                    LIMIT 1
                """)

                row = cursor.fetchone()

                if row:
                    return {
                        'id': row['id'],
                        'url': row['url'],
                        'doc_type': row['doc_type'] if 'doc_type' in row.keys() else 'pdf',
                        'status': row['status'],
                        'added_at': row['added_at'],
                        'retry_count': row['retry_count'],
                        'max_retries': row['max_retries'],
                        'metadata': json.loads(row['metadata']) if row['metadata'] else None
                    }

                return None

        except Exception as e:
            logger.error(f"Error getting next pending: {e}")
            return None

    def mark_processing(self, queue_id: int) -> bool:
        """
        Mark a queue item as currently processing.

        Args:
            queue_id: Database ID of the queue item

        Returns:
            True if updated successfully
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE background_pdf_queue
                    SET status = 'processing',
                        started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (queue_id,))

                conn.commit()
                logger.debug(f"Marked queue item {queue_id} as processing")
                return True

        except Exception as e:
            logger.error(f"Error marking as processing: {e}")
            return False

    def mark_completed(
        self,
        queue_id: int,
        result_cache_key: Optional[str] = None
    ) -> bool:
        """
        Mark a queue item as completed.

        Args:
            queue_id: Database ID of the queue item
            result_cache_key: Cache key where result is stored

        Returns:
            True if updated successfully
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE background_pdf_queue
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        result_cache_key = ?
                    WHERE id = ?
                """, (result_cache_key, queue_id))

                conn.commit()
                logger.info(f"Marked queue item {queue_id} as completed")
                return True

        except Exception as e:
            logger.error(f"Error marking as completed: {e}")
            return False

    def mark_failed(
        self,
        queue_id: int,
        error_message: str,
        increment_retry: bool = True
    ) -> bool:
        """
        Mark a queue item as failed and optionally increment retry count.

        Args:
            queue_id: Database ID of the queue item
            error_message: Error description
            increment_retry: Whether to increment retry count

        Returns:
            True if updated successfully
        """
        try:
            with self._get_connection() as conn:
                if increment_retry:
                    # Increment retry and set back to pending for retry
                    conn.execute("""
                        UPDATE background_pdf_queue
                        SET retry_count = retry_count + 1,
                            error_message = ?,
                            status = CASE
                                WHEN retry_count + 1 >= max_retries THEN 'failed'
                                ELSE 'pending'
                            END
                        WHERE id = ?
                    """, (error_message, queue_id))
                else:
                    # Just mark as failed
                    conn.execute("""
                        UPDATE background_pdf_queue
                        SET status = 'failed',
                            error_message = ?
                        WHERE id = ?
                    """, (error_message, queue_id))

                conn.commit()
                logger.warning(f"Marked queue item {queue_id} as failed: {error_message}")
                return True

        except Exception as e:
            logger.error(f"Error marking as failed: {e}")
            return False

    def get_status(self, url: str) -> Optional[str]:
        """
        Get the processing status of a PDF URL.

        Args:
            url: PDF URL to check

        Returns:
            Status string ('pending', 'processing', 'completed', 'failed') or None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT status FROM background_pdf_queue
                    WHERE url = ?
                """, (url,))

                row = cursor.fetchone()
                return row['status'] if row else None

        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return None

    def get_result_cache_key(self, url: str) -> Optional[str]:
        """
        Get the cache key for a completed PDF.

        Args:
            url: PDF URL to check

        Returns:
            Cache key string or None if not completed
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT result_cache_key FROM background_pdf_queue
                    WHERE url = ? AND status = 'completed'
                """, (url,))

                row = cursor.fetchone()
                return row['result_cache_key'] if row else None

        except Exception as e:
            logger.error(f"Error getting cache key: {e}")
            return None

    def get_queue_stats(self) -> Dict[str, int]:
        """
        Get statistics about the queue.

        Returns:
            Dictionary with counts by status
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM background_pdf_queue
                    GROUP BY status
                """)

                stats = {row['status']: row['count'] for row in cursor}

                # Ensure all statuses are present
                for status in ['pending', 'processing', 'completed', 'failed']:
                    if status not in stats:
                        stats[status] = 0

                return stats

        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}

    def get_all_items(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all queue items, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of queue item dictionaries
        """
        try:
            with self._get_connection() as conn:
                if status:
                    cursor = conn.execute("""
                        SELECT * FROM background_pdf_queue
                        WHERE status = ?
                        ORDER BY added_at DESC
                    """, (status,))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM background_pdf_queue
                        ORDER BY added_at DESC
                    """)

                items = []
                for row in cursor:
                    items.append({
                        'id': row['id'],
                        'url': row['url'],
                        'status': row['status'],
                        'added_at': row['added_at'],
                        'started_at': row['started_at'],
                        'completed_at': row['completed_at'],
                        'retry_count': row['retry_count'],
                        'max_retries': row['max_retries'],
                        'error_message': row['error_message'],
                        'result_cache_key': row['result_cache_key'],
                        'metadata': json.loads(row['metadata']) if row['metadata'] else None
                    })

                return items

        except Exception as e:
            logger.error(f"Error getting all items: {e}")
            return []

    def clear_completed(self, older_than_days: int = 7) -> int:
        """
        Clear completed items older than specified days.

        Args:
            older_than_days: Remove items completed more than this many days ago

        Returns:
            Number of items removed
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM background_pdf_queue
                    WHERE status = 'completed'
                    AND completed_at < datetime('now', '-' || ? || ' days')
                """, (older_than_days,))

                conn.commit()
                removed = cursor.rowcount

                if removed > 0:
                    logger.info(f"Cleared {removed} completed items older than {older_than_days} days")

                return removed

        except Exception as e:
            logger.error(f"Error clearing completed items: {e}")
            return 0

    def remove_item(self, url: str) -> bool:
        """
        Remove a specific item from the queue.

        Args:
            url: PDF URL to remove

        Returns:
            True if removed successfully
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    DELETE FROM background_pdf_queue
                    WHERE url = ?
                """, (url,))

                conn.commit()
                logger.info(f"Removed item from queue: {url}")
                return True

        except Exception as e:
            logger.error(f"Error removing item: {e}")
            return False


# Global instance
_queue_service = None


def get_queue_service() -> BackgroundQueueService:
    """Get or create the global queue service instance."""
    global _queue_service
    if _queue_service is None:
        _queue_service = BackgroundQueueService()
    return _queue_service
