import abc
from typing import List, Dict, Any, Optional
import numpy as np
from django.conf import settings
from django.db import connection

from apps.rag.models import KnowledgeChunk


class BaseVectorStoreAdapter(abc.ABC):
    """Abstract interface defining standard vector storage and similarity search contracts."""

    @abc.abstractmethod
    def similarity_search(
        self,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.08,
        approved_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Searches the vector store for top-k similar chunks."""
        pass

    @abc.abstractmethod
    def is_pgvector_active(self) -> bool:
        """Returns True if live PostgreSQL pgvector extension is available."""
        pass


class PgVectorStoreAdapter(BaseVectorStoreAdapter):
    """
    Intended production adapter for PostgreSQL / Supabase pgvector extension.
    Executes native vector distance queries using the pgvector <=> cosine operator
    or Supabase RPC stored procedures.
    """

    def is_pgvector_active(self) -> bool:
        """Checks if PostgreSQL is active and the pgvector extension is installed."""
        db_engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
        if 'postgresql' not in db_engine:
            return False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
                row = cursor.fetchone()
                return bool(row)
        except Exception:
            return False

    def similarity_search(
        self,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.08,
        approved_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Executes native pgvector cosine similarity search in PostgreSQL.
        Falls back to LocalVectorStoreAdapter if running in a non-PostgreSQL environment.
        """
        if not self.is_pgvector_active():
            return LocalVectorStoreAdapter().similarity_search(
                query_vector, top_k=top_k, threshold=threshold, approved_only=approved_only
            )

        # In production Supabase / PostgreSQL:
        # SELECT id, document_id, content, 1 - (embedding <=> %s) AS similarity ...
        vector_str = f"[{','.join(str(v) for v in query_vector)}]"
        filter_clause = "WHERE kd.is_approved_for_rag = TRUE" if approved_only else ""

        raw_sql = f"""
            SELECT kc.id, kc.chunk_index, kc.content, kd.title, kd.category,
                   1 - (kc.metadata->>'embedding')::vector <=> %s::vector AS similarity
            FROM rag_knowledgechunk kc
            JOIN rag_knowledgedocument kd ON kc.document_id = kd.id
            {filter_clause}
            ORDER BY similarity DESC
            LIMIT %s;
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(raw_sql, [vector_str, top_k])
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    sim = float(row[5])
                    if sim >= threshold:
                        results.append({
                            'chunk_id': str(row[0]),
                            'chunk_index': row[1],
                            'content': row[2],
                            'document_title': row[3],
                            'category': row[4],
                            'similarity_score': round(sim, 4),
                        })
                return results
        except Exception:
            # Safe fallback if table lacks native vector cast
            return LocalVectorStoreAdapter().similarity_search(
                query_vector, top_k=top_k, threshold=threshold, approved_only=approved_only
            )


class LocalVectorStoreAdapter(BaseVectorStoreAdapter):
    """
    Academic / Development / SQLite vector similarity store.
    Computes exact dot products against normalized 384-dimensional unit vectors
    stored in KnowledgeChunk.metadata.
    """

    def is_pgvector_active(self) -> bool:
        return False

    def similarity_search(
        self,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.08,
        approved_only: bool = True
    ) -> List[Dict[str, Any]]:
        q_vec = np.array(query_vector, dtype=np.float32)

        qs = KnowledgeChunk.objects.select_related('document')
        if approved_only:
            qs = qs.filter(document__is_approved_for_rag=True)

        scored_results = []
        for chunk in qs:
            meta = chunk.metadata or {}
            c_vec_list = meta.get('embedding')
            if not c_vec_list or len(c_vec_list) != len(query_vector):
                continue

            c_vec = np.array(c_vec_list, dtype=np.float32)
            similarity = float(np.dot(q_vec, c_vec))

            if similarity >= threshold:
                scored_results.append({
                    'chunk_id': str(chunk.id),
                    'document_title': chunk.document.title,
                    'category': chunk.document.get_category_display(),
                    'chunk_index': chunk.chunk_index,
                    'content': chunk.content,
                    'similarity_score': round(similarity, 4),
                })

        scored_results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return scored_results[:top_k]


def get_vector_store_adapter() -> BaseVectorStoreAdapter:
    """Factory returning the active vector store adapter according to environment capability."""
    pg_adapter = PgVectorStoreAdapter()
    if pg_adapter.is_pgvector_active():
        return pg_adapter
    return LocalVectorStoreAdapter()
