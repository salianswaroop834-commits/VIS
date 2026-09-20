from django.db import models
from django.conf import settings
from core.models import AuditableModel
from customers.models import CustomerProfile
from policies.models import Policy
from staff.models import StaffProfile


class ClaimStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Assignment'
    IN_REVIEW = 'IN_REVIEW', 'Under Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    SETTLED = 'SETTLED', 'Settled'


class ClaimType(models.TextChoices):
    ACCIDENT = 'ACCIDENT', 'Accident / Collision'
    THEFT = 'THEFT', 'Vehicle Theft'
    FIRE = 'FIRE', 'Fire Damage'
    NATURAL_DISASTER = 'NATURAL_DISASTER', 'Natural Disaster / Flood'


class ClaimPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class ClaimEventType(models.TextChoices):
    CLAIM_CREATED = 'CLAIM_CREATED', 'Claim Created'
    CLAIM_ASSIGNED = 'CLAIM_ASSIGNED', 'Claim Assigned / Picked Up'
    CLAIM_IN_REVIEW = 'CLAIM_IN_REVIEW', 'Moved to Review'
    CLAIM_REVIEW_STARTED = 'CLAIM_REVIEW_STARTED', 'Claim Review Started'
    DOCUMENT_ADDED = 'DOCUMENT_ADDED', 'Document Uploaded'
    CLAIM_APPROVED = 'CLAIM_APPROVED', 'Claim Approved by Handler'
    CLAIM_REJECTED = 'CLAIM_REJECTED', 'Claim Rejected by Handler'
    CLAIM_SETTLED = 'CLAIM_SETTLED', 'Claim Settled (Simulated Payout)'
    CLAIM_NOTE_ADDED = 'CLAIM_NOTE_ADDED', 'Claim Note Added'


class Claim(AuditableModel):
    """
    Vehicle Insurance Claim entity.
    Guarantees that:
    1. Claims can only be filed against active authorized policies.
    2. Customers cannot assign handlers; claims start as PENDING (handler=None).
    3. Handlers self-assign claims from the shared queue to move to IN_REVIEW.
    4. Only human handlers can approve (with settlement) or reject (with reason).
    """
    claim_number = models.CharField(max_length=40, unique=True, db_index=True)
    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT,
        related_name='claims',
    )
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.PROTECT,
        related_name='claims',
    )
    handler = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handled_claims',
        help_text='Claims handler assigned to this claim; null while in pending queue.',
    )
    incident_date = models.DateTimeField(db_index=True)
    incident_location = models.CharField(max_length=255)
    incident_description = models.TextField()
    claim_type = models.CharField(
        max_length=30,
        choices=ClaimType.choices,
        default=ClaimType.ACCIDENT,
        db_index=True,
    )
    claim_severity = models.CharField(max_length=30, default='MODERATE')
    estimated_loss_amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    settlement_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Authorized payout finalized by human claims handler',
    )
    settlement_reference = models.CharField(
        max_length=64,
        blank=True,
        help_text='Simulated payment reference for settled claims',
    )
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when claim simulated settlement was finalized',
    )
    rejection_reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ClaimStatus.choices,
        default=ClaimStatus.PENDING,
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=ClaimPriority.choices,
        default=ClaimPriority.MEDIUM,
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Claim'
        verbose_name_plural = 'Claims'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(status=ClaimStatus.PENDING) & models.Q(handler__isnull=False)),
                name='chk_pending_claim_handler_null',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            orig = Claim.objects.filter(pk=self.pk).values('status').first()
            if orig:
                from core.services import ServiceValidationError
                orig_status = orig['status']
                if orig_status in (ClaimStatus.REJECTED, ClaimStatus.SETTLED) and self.status != orig_status:
                    raise ServiceValidationError(
                        f"Cannot modify claim in terminal state '{orig_status}'. Finalized claims cannot be reopened."
                    )
                if orig_status == ClaimStatus.APPROVED and self.status not in (ClaimStatus.APPROVED, ClaimStatus.SETTLED):
                    raise ServiceValidationError(
                        f"Cannot modify approved claim to '{self.status}'. Approved claims can only proceed to SETTLED."
                    )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.claim_number} - {self.policy.policy_number} ({self.status})"

    @property
    def vehicle(self):
        return self.policy.vehicle


class ClaimDocument(AuditableModel):
    """Uploaded evidence and supporting documentation for a claim."""
    class DocType(models.TextChoices):
        POLICE_REPORT = 'POLICE_REPORT', 'Police First Information Report'
        DAMAGE_PHOTO = 'DAMAGE_PHOTO', 'Vehicle Damage Photo'
        REPAIR_ESTIMATE = 'REPAIR_ESTIMATE', 'Repair Garage Estimate'
        DRIVING_LICENSE = 'DRIVING_LICENSE', 'Driver License Copy'
        OTHER = 'OTHER', 'Other Supporting Document'

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(max_length=30, choices=DocType.choices)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='claims/documents/%Y/%m/')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_claim_documents',
    )
    verification_status = models.CharField(
        max_length=30,
        default='PENDING',
        choices=[('PENDING', 'Pending Verification'), ('VERIFIED', 'Verified'), ('REJECTED', 'Rejected')],
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_claim_documents',
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Claim Document'
        verbose_name_plural = 'Claim Documents'


class ClaimEvent(AuditableModel):
    """Immutable audit trail of all lifecycle events and state transitions."""
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name='events',
    )
    event_type = models.CharField(max_length=30, choices=ClaimEventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor_role = models.CharField(max_length=30)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Claim Event'
        verbose_name_plural = 'Claim Events'
        ordering = ['created_at']
