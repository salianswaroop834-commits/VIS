from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import AuditableModel
from accounts.models import UserRole


class StaffStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ON_LEAVE = 'ON_LEAVE', 'On Leave'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    INACTIVE = 'INACTIVE', 'Inactive'


class StaffProfile(AuditableModel):
    """
    Central organizational profile entity storing employee-level information.
    Serves as the parent anchor for specialized staff roles (Underwriters, Claims Handlers).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
    )
    staff_code = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        help_text='Unique employee identifier e.g., UW-102 or CH-405',
    )
    department = models.CharField(max_length=100, default='Operations')
    designation = models.CharField(max_length=100, default='Operational Specialist')
    phone_contact = models.CharField(max_length=20, blank=True)
    joining_date = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=StaffStatus.choices,
        default=StaffStatus.ACTIVE,
        db_index=True,
    )
    assigned_region = models.CharField(max_length=100, default='National')

    # Retained for full backward compatibility across existing claims and policies queries
    max_claim_approval_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('50000.00'),
        help_text='Maximum single-claim settlement amount this handler can authorize',
    )

    class Meta:
        verbose_name = 'Staff Profile'
        verbose_name_plural = 'Staff Profiles'
        ordering = ['staff_code']

    def __str__(self):
        return f"{self.staff_code} - {self.user.get_full_name() or self.user.email} ({self.user.role})"

    @property
    def is_active_staff(self) -> bool:
        return self.status == StaffStatus.ACTIVE and self.user.is_active


class UnderwriterProfile(AuditableModel):
    """
    Specialized business profile for insurance Underwriters.
    Governs policy issuance authority, risk licensing, and portfolio scopes.
    """
    staff_profile = models.OneToOneField(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name='underwriter_profile',
    )
    underwriting_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('2500000.00'),
        help_text='Maximum vehicle IDV / policy coverage this underwriter can approve without escalation',
    )
    license_number = models.CharField(
        max_length=50,
        blank=True,
        help_text='State or statutory insurance underwriting license code',
    )
    specialization = models.CharField(
        max_length=100,
        default='General Motor',
        help_text='Underwriting specialization (e.g. Commercial Fleets, Private Passenger, EV)',
    )
    portfolio_name = models.CharField(
        max_length=100,
        default='Standard Personal Lines',
        help_text='Assigned risk portfolio book of business',
    )
    status = models.CharField(
        max_length=20,
        choices=StaffStatus.choices,
        default=StaffStatus.ACTIVE,
    )

    class Meta:
        verbose_name = 'Underwriter Profile'
        verbose_name_plural = 'Underwriter Profiles'

    def __str__(self):
        return f"Underwriter {self.staff_profile.staff_code} (Limit: {self.underwriting_limit:,.2f})"


class ClaimsHandlerProfile(AuditableModel):
    """
    Specialized business profile for Claims Handlers.
    Governs settlement authorization limits, caseload capacity, and assignment status.
    """
    staff_profile = models.OneToOneField(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name='claims_handler_profile',
    )
    max_claim_approval_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('50000.00'),
        help_text='Maximum single-claim settlement amount this handler can approve',
    )
    active_claim_capacity = models.PositiveIntegerField(
        default=25,
        help_text='Maximum concurrent active claims this handler can hold in review',
    )
    specialization_team = models.CharField(
        max_length=100,
        default='General Claims',
        help_text='Specialized unit (e.g. Rapid Settlement, Total Loss, Bodily Injury)',
    )
    status = models.CharField(
        max_length=20,
        choices=StaffStatus.choices,
        default=StaffStatus.ACTIVE,
    )

    class Meta:
        verbose_name = 'Claims Handler Profile'
        verbose_name_plural = 'Claims Handler Profiles'

    def __str__(self):
        return f"Handler {self.staff_profile.staff_code} (Approval Limit: {self.max_claim_approval_limit:,.2f})"
