import pytest
import numpy as np
from django.urls import reverse
from accounts.models import User, UserRole
from rag.models import KnowledgeDocument, KnowledgeChunk
from rag.services.rag_service import RagService


@pytest.mark.django_db
class TestPhase9RagRetrieval:
    """
    Test suite verifying Phase 9 RAG knowledge ingestion, semantic embeddings,
    cosine similarity retrieval, and responsible AI fallback behavior.
    """

    @pytest.fixture(autouse=True)
    def setup_corpus(self):
        # Automatically ingest official documentation before each test
        RagService.ingest_corpus()

    @pytest.fixture
    def admin_user(self):
        return User.objects.create_user(
            username='admin_rag',
            email='admin_rag@nexisure.test',
            first_name='Admin',
            last_name='RAG',
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )

    def test_corpus_ingestion_and_embedding_dimensions(self):
        docs_count = KnowledgeDocument.objects.count()
        chunks_count = KnowledgeChunk.objects.count()

        assert docs_count >= 5
        assert chunks_count >= 15

        # Check vector dimension and unit normalization on sample chunk
        sample_chunk = KnowledgeChunk.objects.first()
        emb = sample_chunk.metadata.get('embedding')
        assert emb is not None
        assert len(emb) == 384

        # Unit norm check (L2 norm should equal ~1.0)
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 1e-3

    def test_rag_retrieval_relevance_for_zero_depreciation(self):
        query = "What is covered under Zero Depreciation bumper to bumper?"
        results = RagService.retrieve(query, top_k=3)

        assert len(results) >= 1
        top_result = results[0]
        assert 'Zero Depreciation' in top_result['document_title'] or 'Comprehensive' in top_result['document_title']
        assert top_result['similarity_score'] > 0.10

    def test_rag_retrieval_exclusions_for_intoxication(self):
        query = "Is accident caused by driving under influence of alcohol covered?"
        answer_data = RagService.answer_query(query)

        assert answer_data['is_grounded'] is True
        assert any('Exclusion' in src for src in answer_data['sources']) or 'Intoxication' in answer_data['answer'] or 'alcohol' in answer_data['answer'].lower()
        assert 'RESPONSIBLE AI NOTICE' in answer_data['answer']

    def test_safety_fallback_for_irrelevant_out_of_scope_query(self):
        query = "What is the capital city of Australia and recipe for pancakes?"
        answer_data = RagService.answer_query(query)

        assert answer_data['is_grounded'] is False
        assert answer_data['confidence_score'] == 0.0
        assert "unable to find verified Nexisure vehicle insurance documentation" in answer_data['answer']

    def test_rag_views_search_and_document_listing(self, client):
        # 1. Document listing view
        list_url = reverse('rag:list')
        resp_list = client.get(list_url)
        assert resp_list.status_code == 200
        content_list = resp_list.content.decode('utf-8')
        assert 'Official Policy Documentation & Clauses' in content_list
        assert 'Comprehensive' in content_list

        # 2. Semantic Search View with Query
        search_url = reverse('rag:search') + '?q=What+is+the+deductible%3F'
        resp_search = client.get(search_url)
        assert resp_search.status_code == 200
        content_search = resp_search.content.decode('utf-8')
        assert 'Grounded Policy Guidance' in content_search or 'Deductibles' in content_search
        assert 'Confidence:' in content_search

    def test_rag_staff_ingest_view(self, client, admin_user):
        ingest_url = reverse('rag:ingest')
        client.force_login(admin_user)
        resp = client.post(ingest_url)
        assert resp.status_code == 302
        assert reverse('rag:list') in resp.url
