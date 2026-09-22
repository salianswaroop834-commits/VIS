from django.db import models
from core.models import AuditableModel


class KnowledgeCategory(models.TextChoices):
    POLICY_WORDING = 'POLICY_WORDING', 'Policy Wording & Definitions'
    COVERAGE_DETAILS = 'COVERAGE_DETAILS', 'Coverage Details & Exclusions'
    CLAIM_PROCEDURE = 'CLAIM_PROCEDURE', 'Approved Claims Procedures'
    CLAIM_DOCUMENT_REQ = 'CLAIM_DOCUMENT_REQ', 'Claim Document Requirements'
    CLAIM_FAQ = 'CLAIM_FAQ', 'Claim FAQs'
    SERVICING_GUIDE = 'SERVICING_GUIDE', 'Policy Servicing Procedures'
    RENEWAL_INFO = 'RENEWAL_INFO', 'Renewal Rules & Procedures'


class KnowledgeDocument(AuditableModel):
    """
    Approved official vehicle insurance reference document.
    Serves as the ground-truth corpus for the RAG retriever.
    """
    title = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=40, choices=KnowledgeCategory.choices, db_index=True)
    version = models.CharField(max_length=20, default='1.0')
    source_reference = models.CharField(max_length=255)
    is_approved_for_rag = models.BooleanField(default=True, db_index=True)
    content_raw = models.TextField(help_text='Full extracted text')

    class Meta:
        verbose_name = 'Knowledge Document'
        verbose_name_plural = 'Knowledge Documents'
        ordering = ['title']

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class KnowledgeChunk(AuditableModel):
    """
    Segmented text chunk for vector similarity retrieval in Supabase pgvector.
    """
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name='chunks',
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    supabase_embedding_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text='Identifier in Supabase pgvector table',
    )
    metadata = models.JSONField(default=dict)

    class Meta:
        verbose_name = 'Knowledge Chunk'
        verbose_name_plural = 'Knowledge Chunks'
        unique_together = ('document', 'chunk_index')
        ordering = ['document', 'chunk_index']

    def __str__(self):
        return f"{self.document.title} - Chunk #{self.chunk_index}"
