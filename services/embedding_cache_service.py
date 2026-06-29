"""
Embedding Cache Service
Manages storage and retrieval of document embeddings in SQLite
"""
import sqlite3
import json
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np


class EmbeddingCacheService:
    """
    Cache service for document embeddings
    - Stores embeddings in SQLite
    - Tracks embedding status
    - Provides semantic search capabilities
    """

    def __init__(self, db_path: str = "db/serper_cache.db"):
        """Initialize cache service with database connection"""
        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Ensure embedding tables exist"""
        schema_file = Path(__file__).parent.parent / "db" / "cache_schema_embeddings.sql"

        if schema_file.exists():
            conn = self._get_connection()
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
            conn.close()

    def check_embedding_status(self, url: str) -> Optional[Dict]:
        """
        Check if document already has embeddings

        Returns:
            Dict with status info or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, total_chunks, processed_chunks, error_message, updated_at
            FROM embedding_status
            WHERE url = ?
        """, (url,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'status': row['status'],
                'total_chunks': row['total_chunks'],
                'processed_chunks': row['processed_chunks'],
                'error_message': row['error_message'],
                'updated_at': row['updated_at']
            }
        return None

    def record_embedding_start(self, url: str, doc_type: str, total_chunks: int):
        """Mark document as being embedded"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO embedding_status
            (url, doc_type, status, total_chunks, processed_chunks, updated_at)
            VALUES (?, ?, 'processing', ?, 0, CURRENT_TIMESTAMP)
        """, (url, doc_type, total_chunks))

        conn.commit()
        conn.close()

    def record_embedding_success(self, url: str):
        """Mark embedding as completed"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE embedding_status
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE url = ?
        """, (url,))

        conn.commit()
        conn.close()

    def record_embedding_failure(self, url: str, error: str):
        """Record embedding failure"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE embedding_status
            SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE url = ?
        """, (error, url))

        conn.commit()
        conn.close()

    def store_embeddings(self, embeddings_data: List[Dict]):
        """
        Store multiple embeddings

        Args:
            embeddings_data: List of dicts with:
                - url, doc_type, doc_id, chunk_id, chunk_text
                - embedding (list of floats)
                - word_count, char_count
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        for item in embeddings_data:
            # Serialize embedding as JSON
            embedding_json = json.dumps(item['embedding'])

            cursor.execute("""
                INSERT OR REPLACE INTO document_embeddings
                (url, doc_type, doc_id, chunk_id, chunk_text, embedding,
                 embedding_model, word_count, char_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item['url'],
                item['doc_type'],
                item['doc_id'],
                item['chunk_id'],
                item['chunk_text'],
                embedding_json,
                'text-embedding-3-small',
                item.get('word_count', 0),
                item.get('char_count', 0)
            ))

        conn.commit()
        conn.close()

    def get_document_embeddings(self, url: str) -> List[Dict]:
        """
        Retrieve all embeddings for a document

        Returns:
            List of dicts with chunk_id, chunk_text, embedding
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT chunk_id, chunk_text, embedding, word_count, char_count
            FROM document_embeddings
            WHERE url = ?
            ORDER BY chunk_id
        """, (url,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'chunk_id': row['chunk_id'],
                'chunk_text': row['chunk_text'],
                'embedding': json.loads(row['embedding']),
                'word_count': row['word_count'],
                'char_count': row['char_count']
            })

        conn.close()
        return results

    def get_all_embeddings(
        self,
        limit: int = 10000,
        doc_type_filter: Optional[str] = None,
        url_filter: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get all embeddings for semantic search

        Args:
            limit: Maximum number of embeddings to return
            doc_type_filter: Filter by 'html' or 'pdf' (None for all)
            url_filter: Filter by specific URLs (None for all)

        Returns:
            List of dicts with url, doc_type, chunk_id, chunk_text, embedding
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build query with filters
        query = """
            SELECT url, doc_type, doc_id, chunk_id, chunk_text, embedding
            FROM document_embeddings
        """
        where_clauses = []
        params = []

        if doc_type_filter:
            where_clauses.append("doc_type = ?")
            params.append(doc_type_filter)

        if url_filter:
            # Use IN clause for URL filtering
            placeholders = ','.join(['?' for _ in url_filter])
            where_clauses.append(f"url IN ({placeholders})")
            params.extend(url_filter)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)

        results = []
        for row in cursor.fetchall():
            results.append({
                'url': row['url'],
                'doc_type': row['doc_type'],
                'doc_id': row['doc_id'],
                'chunk_id': row['chunk_id'],
                'chunk_text': row['chunk_text'],
                'embedding': json.loads(row['embedding'])
            })

        conn.close()
        return results

    def delete_document_embeddings(self, url: str):
        """Delete all embeddings for a document"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM document_embeddings WHERE url = ?", (url,))
        cursor.execute("DELETE FROM embedding_status WHERE url = ?", (url,))

        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict:
        """Get embedding statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM document_embeddings")
        total_embeddings = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(DISTINCT url) as count FROM document_embeddings")
        total_documents = cursor.fetchone()['count']

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM embedding_status
            GROUP BY status
        """)
        status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

        conn.close()

        return {
            'total_embeddings': total_embeddings,
            'total_documents': total_documents,
            'status_counts': status_counts
        }
