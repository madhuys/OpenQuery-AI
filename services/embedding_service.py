"""
Azure OpenAI Embedding Service
Handles document embedding generation using Azure OpenAI text-embedding-3-small model
"""
from typing import List, Dict, Optional
from openai import AzureOpenAI
from config.settings import AppSettings, SETTINGS_FILE
from services.embedding_cache_service import EmbeddingCacheService
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading


class AzureOpenAIEmbeddingService:
    """
    Azure OpenAI client wrapper for generating embeddings
    Uses text-embedding-3-small model (1536 dimensions)
    """

    def __init__(self, settings: Optional[AppSettings] = None):
        """Initialize Azure OpenAI client"""
        if settings is None:
            settings = AppSettings.load(SETTINGS_FILE)

        self.settings = settings.embedding

        # Initialize Azure OpenAI client
        self.client = AzureOpenAI(
            azure_endpoint=self.settings.azure_endpoint,
            api_key=self.settings.api_key,
            api_version=self.settings.api_version
        )

        self.deployment_name = self.settings.deployment_name
        self.max_batch_size = self.settings.max_chunk_batch_size

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts

        Args:
            texts: List of text strings (max 100 per Azure API limit)

        Returns:
            List of embedding vectors (each 1536 dimensions)

        Raises:
            Exception: If API call fails
        """
        if not texts:
            return []

        if len(texts) > self.max_batch_size:
            raise ValueError(f"Batch size {len(texts)} exceeds max {self.max_batch_size}")

        # Call Azure OpenAI API
        response = self.client.embeddings.create(
            input=texts,
            model=self.deployment_name
        )

        # Extract embeddings from response
        embeddings = [item.embedding for item in response.data]

        return embeddings


def get_embedding_stats() -> Dict:
    """
    Get statistics about stored embeddings

    Returns:
        Dict with stats: total_documents, total_chunks, total_embeddings
    """
    from services.embedding_cache_service import EmbeddingCacheService

    cache_service = EmbeddingCacheService()
    conn = cache_service._get_connection()
    cursor = conn.cursor()

    try:
        # Count total documents with embeddings
        cursor.execute("""
            SELECT COUNT(DISTINCT url) as count
            FROM embedding_status
            WHERE status = 'completed'
        """)
        total_documents = cursor.fetchone()['count']

        # Count total chunks across all documents
        cursor.execute("""
            SELECT SUM(total_chunks) as count
            FROM embedding_status
            WHERE status = 'completed'
        """)
        result = cursor.fetchone()
        total_chunks = result['count'] if result['count'] else 0

        # Count total embedding records in embeddings table
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM embeddings
        """)
        total_embeddings = cursor.fetchone()['count']

        return {
            'total_documents': total_documents,
            'total_chunks': total_chunks,
            'total_embeddings': total_embeddings
        }
    except Exception as e:
        # If tables don't exist yet, return zeros
        return {
            'total_documents': 0,
            'total_chunks': 0,
            'total_embeddings': 0
        }
    finally:
        conn.close()


def embed_document_sync(
    url: str,
    doc_type: str,
    chunks: List[Dict],
    doc_id: str
) -> bool:
    """
    Synchronously embed all chunks of a document
    Called from HTML/PDF processing worker after JSON save

    Args:
        url: Document URL
        doc_type: 'html' or 'pdf'
        chunks: List of chunk dicts with 'text', 'word_count', 'char_count', etc.
        doc_id: Document fingerprint/hash

    Returns:
        True if successful, False otherwise
    """
    # Load settings
    settings = AppSettings.load(SETTINGS_FILE)

    # Check if embeddings are enabled
    if not settings.embedding.enabled:
        return False

    # Initialize services
    cache_service = EmbeddingCacheService()
    embedding_service = AzureOpenAIEmbeddingService(settings)

    try:
        # Check if already embedded
        status = cache_service.check_embedding_status(url)
        if status and status['status'] == 'completed':
            # print(f"[EMBED] ⏭️  Already embedded: {url}")
            return True

        # Extract chunk texts
        chunk_texts = []
        for chunk in chunks:
            # Handle different chunk structures
            if isinstance(chunk, dict):
                # HTML format: {'text': '...', 'word_count': ...}
                text = chunk.get('text', chunk.get('content', ''))
            else:
                # Fallback: treat as string
                text = str(chunk)

            if text and text.strip():
                chunk_texts.append(text.strip())

        if not chunk_texts:
            # print(f"[EMBED] ⚠️  No valid chunks to embed: {url}")
            return False

        total_chunks = len(chunk_texts)

        # Record embedding start
        cache_service.record_embedding_start(url, doc_type, total_chunks)

        # Process in batches with intelligent sizing
        # Azure OpenAI has 8192 token limit per request
        # Estimate ~4 chars per token, so max ~32k chars per batch
        # Use smaller batch sizes for safety
        all_embeddings = []
        max_batch_size = settings.embedding.max_chunk_batch_size

        # Dynamic batching based on content length
        i = 0
        batch_num = 0
        while i < total_chunks:
            # Determine dynamic batch size based on chunk lengths
            batch_texts = []
            total_chars = 0
            max_chars_per_batch = 25000  # Safe limit (~6250 tokens)

            while i < total_chunks and len(batch_texts) < max_batch_size:
                chunk_len = len(chunk_texts[i])
                # If adding this chunk would exceed limit, stop (unless batch is empty)
                if batch_texts and (total_chars + chunk_len) > max_chars_per_batch:
                    break
                batch_texts.append(chunk_texts[i])
                total_chars += chunk_len
                i += 1

            batch_num += 1
            total_batches = (total_chunks + max_batch_size - 1) // max_batch_size

            # print(f"[EMBED] 🔄 Batch {batch_num} ({len(batch_texts)} chunks, {total_chars:,} chars): {url}")

            # Generate embeddings for this batch
            try:
                batch_embeddings = embedding_service.embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                # If batch fails due to token limit, retry with smaller batches
                if "maximum context length" in str(e).lower():
                    # print(f"[EMBED] ⚠️ Batch too large, splitting into smaller batches...")
                    # Split into individual chunks
                    for single_text in batch_texts:
                        single_embedding = embedding_service.embed_batch([single_text])
                        all_embeddings.extend(single_embedding)
                else:
                    raise

        # Prepare embedding data for storage
        embeddings_data = []
        for chunk_idx, (chunk, embedding) in enumerate(zip(chunks, all_embeddings)):
            # Extract metadata from original chunk
            if isinstance(chunk, dict):
                text = chunk.get('text', chunk.get('content', ''))
                word_count = chunk.get('word_count', 0)
                char_count = chunk.get('char_count', len(text))
            else:
                text = str(chunk)
                word_count = len(text.split())
                char_count = len(text)

            embeddings_data.append({
                'url': url,
                'doc_type': doc_type,
                'doc_id': doc_id,
                'chunk_id': chunk_idx,
                'chunk_text': text,
                'embedding': embedding,
                'word_count': word_count,
                'char_count': char_count
            })

        # Store all embeddings in database
        cache_service.store_embeddings(embeddings_data)

        # Record success
        cache_service.record_embedding_success(url)

        # print(f"[EMBED] ✅ Embedded {total_chunks} chunks: {url}")
        return True

    except Exception as e:
        error_msg = str(e)
        # print(f"[EMBED] ❌ Failed: {url} - {error_msg}")

        # Record failure
        cache_service.record_embedding_failure(url, error_msg)
        return False


def embed_document_async(
    url: str,
    doc_type: str,
    chunks: List[Dict],
    doc_id: str
) -> None:
    """
    Fire-and-forget async embedding - starts embedding in background thread
    Returns immediately without blocking the worker/HTTP response

    This allows the document analysis to complete quickly while embeddings
    happen in parallel in the background.

    Args:
        url: Document URL
        doc_type: 'html' or 'pdf'
        chunks: List of chunk dicts
        doc_id: Document fingerprint/hash
    """
    # Start embedding in a background thread (daemon=True means it won't block process exit)
    thread = threading.Thread(
        target=embed_document_sync,
        args=(url, doc_type, chunks, doc_id),
        daemon=True,
        name=f"Embedding-{doc_id[:8]}"
    )
    thread.start()
    # print(f"[EMBED] 🚀 Started background embedding thread for: {url}")
