"""
Semantic Search Service
Provides semantic search capabilities over embedded documents
"""
from typing import List, Dict, Optional
import numpy as np
from services.embedding_service import AzureOpenAIEmbeddingService
from services.embedding_cache_service import EmbeddingCacheService
from config.settings import AppSettings, SETTINGS_FILE


class SemanticSearchService:
    """
    Semantic search service using cosine similarity
    Searches across embedded document chunks
    """

    def __init__(self, settings: Optional[AppSettings] = None):
        """Initialize search service"""
        if settings is None:
            settings = AppSettings.load(SETTINGS_FILE)

        self.settings = settings
        self.embedding_service = AzureOpenAIEmbeddingService(settings)
        self.cache_service = EmbeddingCacheService()

        # Query embedding cache (in-memory for session)
        self._query_cache = {}  # {query: embedding}

        # Document embeddings cache (in-memory for session)
        # Key: frozenset of URL filter (for uniqueness)
        # Value: list of embedding dicts
        self._embeddings_cache = {}  # {frozenset(urls): embeddings}

        # Preload all embeddings on initialization (warm cache)
        self._preload_embeddings()

    def _preload_embeddings(self):
        """
        Preload all embeddings on service initialization to warm the cache.
        This makes the first search instant instead of waiting for DB load.
        """
        try:
            import time
            start = time.time()
            all_embeddings = self.cache_service.get_all_embeddings(limit=10000)

            if all_embeddings:
                # Cache under '__all__' key
                cache_key = frozenset(['__all__'])
                self._embeddings_cache[cache_key] = all_embeddings
                elapsed = time.time() - start
                print(f"[SEARCH-INIT] ✅ Preloaded {len(all_embeddings)} embeddings in {elapsed:.3f}s")
            else:
                print(f"[SEARCH-INIT] ℹ️  No embeddings found to preload")
        except Exception as e:
            print(f"[SEARCH-INIT] ⚠️  Failed to preload embeddings: {e}")

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Similarity score between -1 and 1 (typically 0 to 1 for embeddings)
        """
        # Convert to numpy arrays
        a = np.array(vec1)
        b = np.array(vec2)

        # Calculate cosine similarity
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def search(
        self,
        query: str,
        limit: int = 20,
        doc_type_filter: Optional[str] = None,
        score_threshold: Optional[float] = None,
        url_filter: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Perform semantic search across embedded documents

        Args:
            query: Search query text
            limit: Maximum number of results to return
            doc_type_filter: Filter by 'html' or 'pdf' (None for all)
            score_threshold: Minimum similarity score (0-1) to include in results
            url_filter: Filter by specific URLs (None for all)

        Returns:
            List of dicts with:
                - url: Document URL
                - doc_type: 'html' or 'pdf'
                - chunk_id: Chunk index
                - chunk_text: Chunk content
                - similarity_score: Cosine similarity (0-1)
        """
        # Check if embeddings are enabled
        if not self.settings.embedding.enabled:
            return []

        # Use default threshold if not provided
        if score_threshold is None:
            score_threshold = self.settings.embedding.similarity_threshold

        # Step 1: Embed the query (with caching)
        import time
        embed_start = time.time()

        if query in self._query_cache:
            query_embedding = self._query_cache[query]
            print(f"[SEARCH] 🚀 Using cached query embedding")
        else:
            try:
                query_embedding = self.embedding_service.embed_batch([query])[0]
                self._query_cache[query] = query_embedding
                print(f"[SEARCH] ⏱️  Query embedding: {time.time() - embed_start:.3f}s")
            except Exception as e:
                print(f"[SEARCH] ❌ Failed to embed query: {e}")
                return []

        # Step 2: Retrieve embeddings (with caching by URL set)
        db_start = time.time()
        print(f"[SEARCH] 📋 Query: '{query}', Threshold: {score_threshold}, URL Filter: {len(url_filter) if url_filter else 'None'}")
        if url_filter:
            print(f"[SEARCH] 🔗 Filtering by URLs: {url_filter[:3]}{'...' if len(url_filter) > 3 else ''}")

        # OPTIMIZATION: Check if we have the full preloaded cache, then filter in-memory
        all_cache_key = frozenset(['__all__'])
        if all_cache_key in self._embeddings_cache:
            # We have all embeddings preloaded - filter in memory (FAST!)
            preloaded = self._embeddings_cache[all_cache_key]

            if url_filter:
                # Filter to only the requested URLs
                url_set = set(url_filter)
                all_embeddings = [item for item in preloaded if item['url'] in url_set]
                print(f"[SEARCH] 🚀 Filtered preloaded cache: {len(preloaded)} → {len(all_embeddings)} chunks ({time.time() - db_start:.3f}s)")
            else:
                # Use all preloaded embeddings
                all_embeddings = preloaded
                print(f"[SEARCH] 🚀 Using full preloaded cache: {len(all_embeddings)} chunks")
        else:
            # Fallback: Query database (first search or cache not available)
            all_embeddings = self.cache_service.get_all_embeddings(
                limit=10000,  # Get all available embeddings
                doc_type_filter=doc_type_filter,
                url_filter=url_filter
            )

            if not all_embeddings:
                print(f"[SEARCH] ⚠️  No embeddings found in database (url_filter={bool(url_filter)})")
                return []

            print(f"[SEARCH] ⏱️  Database retrieval: {time.time() - db_start:.3f}s")

        print(f"[SEARCH] 🔍 Searching across {len(all_embeddings)} chunks...")

        # Step 3: Calculate similarity using vectorized operations (MUCH FASTER!)
        similarity_start = time.time()

        # Convert to numpy matrix for vectorized operations
        query_vec = np.array(query_embedding)
        embeddings_matrix = np.array([item['embedding'] for item in all_embeddings])

        # Compute all similarities at once (vectorized)
        # Shape: (n_chunks, embedding_dim) @ (embedding_dim,) = (n_chunks,)
        similarities = np.dot(embeddings_matrix, query_vec) / (
            np.linalg.norm(embeddings_matrix, axis=1) * np.linalg.norm(query_vec)
        )

        print(f"[SEARCH] ⏱️  Vectorized similarity: {time.time() - similarity_start:.3f}s")

        # Step 4: Filter by threshold and build results
        results = []
        for i, item in enumerate(all_embeddings):
            similarity = similarities[i]
            if similarity >= score_threshold:
                results.append({
                    'url': item['url'],
                    'doc_type': item['doc_type'],
                    'doc_id': item['doc_id'],
                    'chunk_id': item['chunk_id'],
                    'chunk_text': item['chunk_text'],
                    'similarity_score': float(similarity)
                })

        # Step 4: Sort by similarity (highest first)
        results.sort(key=lambda x: x['similarity_score'], reverse=True)

        # Step 5: Limit results
        results = results[:limit]

        print(f"[SEARCH] ✅ Found {len(results)} results above threshold {score_threshold}")

        return results

    def get_statistics(self) -> Dict:
        """Get embedding statistics for display"""
        return self.cache_service.get_statistics()
