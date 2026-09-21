from django.db import models
from django.conf import settings
from core.models import AuditableModel


class MessageSender(models.TextChoices):
    USER = 'USER', 'User'
    ASSISTANT = 'ASSISTANT', 'AI Assistant'
    SYSTEM = 'SYSTEM', 'System'


class ChatSession(AuditableModel):
    """
    Stateful conversational session.
    Tracks authentication, intent, and multi-turn transaction confirmations.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_sessions',
    )
    session_key = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=150, default='Vehicle Insurance Assistance')
    pending_transaction = models.JSONField(
        null=True,
        blank=True,
        help_text='Payload awaiting explicit customer confirmation before tool invocation',
    )

    class Meta:
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'
        ordering = ['-created_at']

    def __str__(self):
        user_display = self.user.email if self.user else f"Guest ({self.session_key[:8]})"
        return f"Chat Session: {user_display} ({self.created_at:%Y-%m-%d %H:%M})"


class ChatMessage(AuditableModel):
    """Individual message within a conversation."""
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.CharField(max_length=20, choices=MessageSender.choices)
    content = models.TextField()
    sources = models.JSONField(
        default=list,
        help_text='Retrieved RAG knowledge chunks and policy references',
    )

    class Meta:
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['created_at']


class ChatbotToolCall(AuditableModel):
    """
    Controlled transactional tool execution record.
    Guarantees backend-owned authorization, validation, and auditability.
    """
    class ExecutionStatus(models.TextChoices):
        PROPOSED = 'PROPOSED', 'Proposed / Pending Confirmation'
        CONFIRMED = 'CONFIRMED', 'Confirmed by Customer'
        EXECUTED = 'EXECUTED', 'Executed Successfully'
        BLOCKED = 'BLOCKED', 'Blocked by Guardrail'
        FAILED = 'FAILED', 'Failed'

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='tool_calls',
    )
    tool_name = models.CharField(max_length=60, db_index=True)
    parameters = models.JSONField(default=dict)
    execution_status = models.CharField(
        max_length=30,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.PROPOSED,
    )
    result_payload = models.JSONField(default=dict)
    guardrail_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Chatbot Tool Call'
        verbose_name_plural = 'Chatbot Tool Calls'
        ordering = ['-created_at']
