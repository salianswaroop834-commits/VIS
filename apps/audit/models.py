from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied
from core.models import UUIDModel


class AuditAction(models.TextChoices):
    # Staff operations
    STAFF_CREATED = 'STAFF_CREATED', 'Staff Created'
    STAFF_UPDATED = 'STAFF_UPDATED', 'Staff Updated'
    STAFF_DELETED = 'STAFF_DELETED', 'Staff Deleted'
    STAFF_REASSIGNED = 'STAFF_REASSIGNED', 'Staff Workload Reassigned'

    # Customer & Auth operations
    CUSTOMER_CREATED = 'CUSTOMER_CREATED', 'Customer Created'
    CUSTOMER_UPDATED = 'CUSTOMER_UPDATED', 'Customer Updated'
    USER_LOGIN = 'USER_LOGIN', 'User Logged In'
    USER_LOGOUT = 'USER_LOGOUT', 'User Logged Out'
    USER_ROLE_CHANGED = 'USER_ROLE_CHANGED', 'User Role Changed'

    # Vehicle operations
    VEHICLE_CREATED = 'VEHICLE_CREATED', 'Vehicle Created'
    VEHICLE_UPDATED = 'VEHICLE_UPDATED', 'Vehicle Updated'
    VEHICLE_DEACTIVATED = 'VEHICLE_DEACTIVATED', 'Vehicle Deactivated'

    # Quotation operations
    QUOTATION_CREATED = 'QUOTATION_CREATED', 'Quotation Created'
    QUOTATION_ACCEPTED = 'QUOTATION_ACCEPTED', 'Quotation Accepted'

    # Policy operations
    POLICY_CREATED = 'POLICY_CREATED', 'Policy Created'
    POLICY_UPDATED = 'POLICY_UPDATED', 'Policy Updated'
    POLICY_RENEWED = 'POLICY_RENEWED', 'Policy Renewed'
    POLICY_TYPE_CONVERTED = 'POLICY_TYPE_CONVERTED', 'Policy Coverage Converted'
    POLICY_REASSIGNED = 'POLICY_REASSIGNED', 'Policy Underwriter Reassigned'
    POLICY_CERTIFICATE_GENERATED = 'POLICY_CERTIFICATE_GENERATED', 'Policy Certificate Generated'
    POLICY_ENDORSEMENT_REQUESTED = 'POLICY_ENDORSEMENT_REQUESTED', 'Policy Endorsement Requested'
    POLICY_ENDORSEMENT_APPROVED = 'POLICY_ENDORSEMENT_APPROVED', 'Policy Endorsement Approved'
    POLICY_ENDORSEMENT_REJECTED = 'POLICY_ENDORSEMENT_REJECTED', 'Policy Endorsement Rejected'
    POLICY_CANCELLED = 'POLICY_CANCELLED', 'Policy Cancelled'

    # Claim operations
    CLAIM_CREATED = 'CLAIM_CREATED', 'Claim Created'
    CLAIM_ASSIGNED = 'CLAIM_ASSIGNED', 'Claim Assigned / Picked Up'
    CLAIM_REVIEW_STARTED = 'CLAIM_REVIEW_STARTED', 'Claim Review Started'
    CLAIM_APPROVED = 'CLAIM_APPROVED', 'Claim Approved'
    CLAIM_REJECTED = 'CLAIM_REJECTED', 'Claim Rejected'
    CLAIM_DOCUMENT_ADDED = 'CLAIM_DOCUMENT_ADDED', 'Claim Document Added'
    CLAIM_NOTE_ADDED = 'CLAIM_NOTE_ADDED', 'Claim Note Added'
    CLAIM_SETTLED = 'CLAIM_SETTLED', 'Claim Settled'

    # Service Request operations
    SERVICE_REQUEST_CREATED = 'SERVICE_REQUEST_CREATED', 'Service Request Created'
    SERVICE_REQUEST_UPDATED = 'SERVICE_REQUEST_UPDATED', 'Service Request Updated'
    SERVICE_REQUEST_RESOLVED = 'SERVICE_REQUEST_RESOLVED', 'Service Request Resolved'
    SERVICE_REQUEST_REJECTED = 'SERVICE_REQUEST_REJECTED', 'Service Request Rejected'

    # KYC & Identity operations
    KYC_VERIFICATION_STARTED = 'KYC_VERIFICATION_STARTED', 'KYC Verification Started'
    KYC_VERIFIED = 'KYC_VERIFIED', 'KYC Verified'
    KYC_FAILED = 'KYC_FAILED', 'KYC Verification Failed'
    USER_REGISTERED = 'USER_REGISTERED', 'User Registered'

    # Assignment operations
    CUSTOMER_ASSIGNED = 'CUSTOMER_ASSIGNED', 'Customer Assigned to Staff'
    CUSTOMER_TRANSFERRED = 'CUSTOMER_TRANSFERRED', 'Customer Transferred to Staff'
    CUSTOMER_UNASSIGNED = 'CUSTOMER_UNASSIGNED', 'Customer Unassigned from Staff'
    STAFF_SUSPENDED = 'STAFF_SUSPENDED', 'Staff Suspended'

    # AI & Tool operations
    CHATBOT_TOOL_EXECUTED = 'CHATBOT_TOOL_EXECUTED', 'Chatbot Tool Executed'
    PREDICTION_CREATED = 'PREDICTION_CREATED', 'ML Prediction Created'
    MODEL_VERSION_PROMOTED = 'MODEL_VERSION_PROMOTED', 'Model Version Promoted'
    PAYMENT_PROCESSED = 'PAYMENT_PROCESSED', 'Payment Processed'
    VEHICLE_LOOKUP = 'VEHICLE_LOOKUP', 'Vehicle Registry Lookup'


class AuditLogQuerySet(models.QuerySet):
    """Immutable QuerySet blocking destructive bulk modifications."""

    def update(self, **kwargs):
        raise PermissionDenied("Audit log entries are immutable compliance records. Bulk updates are strictly prohibited.")

    def delete(self):
        raise PermissionDenied("Audit log entries are permanent compliance records. Bulk deletion is strictly prohibited.")


class AuditLog(UUIDModel):
    """
    Immutable compliance audit ledger.
    Captures every state-modifying action across underwriting, claims,
    and automated tool interactions.
    """
    objects = AuditLogQuerySet.as_manager()

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    actor_email = models.CharField(max_length=255, blank=True)
    actor_role = models.CharField(max_length=50, blank=True)
    action = models.CharField(max_length=60, choices=AuditAction.choices, db_index=True)
    target_entity = models.CharField(max_length=60, db_index=True)
    target_id = models.CharField(max_length=64, db_index=True)
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("Audit log entries are immutable and cannot be updated or altered.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit log entries are permanent compliance records and cannot be deleted.")

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.action} on {self.target_entity}:{self.target_id} by {self.actor_email or 'System'}"
