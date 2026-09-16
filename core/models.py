import uuid
from django.db import models
from django.conf import settings


class UUIDModel(models.Model):
    """
    Abstract base model providing a UUID primary key.
    Ensures seamless compatibility with Supabase PostgreSQL UUID primary keys.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """
    Abstract base model providing self-updating creation and modification timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditableModel(UUIDModel, TimeStampedModel):
    """
    Comprehensive abstract base model for enterprise insurance entities.
    Combines UUID primary key, indexed timestamps, and audit metadata.
    """
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


class NotificationType(models.TextChoices):
    RENEWAL_REMINDER = 'RENEWAL_REMINDER', 'Policy Renewal Reminder'
    CLAIM_STATUS = 'CLAIM_STATUS', 'Claim Status Update'
    SERVICE_UPDATE = 'SERVICE_UPDATE', 'Service Request Update'
    SECURITY_ALERT = 'SECURITY_ALERT', 'Account Security Alert'
    GENERAL = 'GENERAL', 'General Notification'


class Notification(AuditableModel):
    """
    In-app user notification entity.
    Supports policy renewal reminders, claim status changes, and security events.
    """
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
        db_index=True,
    )
    is_read = models.BooleanField(default=False, db_index=True)
    action_url = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.email}: {self.title}"
