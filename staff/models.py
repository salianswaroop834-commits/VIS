from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import AuditableModel


class StaffStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ON_LEAVE = 'ON_LEAVE', 'On Leave'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    INACTIVE = 'INACTIVE', 'Inactive'


class StaffDepartment(models.TextChoices):
    UNDERWRITING = 'UNDERWRITING', 'Underwriting'
    CLAIMS = 'CLAIMS', 'Claims'


class Branch(AuditableModel):
    """
    Internal operational branch entity.
    """
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    branch_opening_date = models.DateField(null=True, blank=True)
    office_rent_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )

    class Meta:
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        ordering = ['state', 'city']

    def __str__(self):
        return f"{self.city}, {self.state} Branch"


class StaffProfileManager(models.Manager):
    def create(self, **kwargs):
        user = kwargs.get('user')
        if user:
            existing = self.filter(user=user).first()
            if existing:
                for k, v in kwargs.items():
                    setattr(existing, k, v)
                existing.save()
                return existing
        return super().create(**kwargs)


class StaffProfile(AuditableModel):
    """
    Central organizational profile entity storing employee-level information.
    Serves as the parent anchor for specialized staff roles (Underwriters, Claims Handlers).
    """
    objects = StaffProfileManager()
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
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    department = models.CharField(
        max_length=30,
        choices=StaffDepartment.choices,
        default=StaffDepartment.UNDERWRITING,
        db_index=True,
    )
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
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
    )
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates',
    )
    employee_level = models.CharField(max_length=30, default='L1')
    performance_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
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
        name = f"{self.first_name} {self.last_name}".strip() or self.user.get_full_name() or self.user.email
        return f"{self.staff_code} - {name} ({self.department})"

    @property
    def is_active_staff(self) -> bool:
        return self.status == StaffStatus.ACTIVE and self.user.is_active

    @property
    def assigned_customers(self):
        """Returns QuerySet of CustomerProfiles actively assigned to this staff member."""
        from customers.models import CustomerProfile
        return CustomerProfile.objects.filter(
            staff_assignments__staff=self.user,
            staff_assignments__status='ACTIVE'
        ).distinct()


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
    approval_authority_level = models.CharField(
        max_length=30,
        default='STANDARD',
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
        return f"Underwriter {self.staff_profile.staff_code} (Limit: ₹{self.underwriting_limit:,.2f})"

    @property
    def policies_handled_count(self) -> int:
        return self.staff_profile.underwritten_policies.count()

    @property
    def quotations_reviewed_count(self) -> int:
        return self.staff_profile.quotations.count()


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
        return f"Handler {self.staff_profile.staff_code} (Approval Limit: ₹{self.max_claim_approval_limit:,.2f})"

    @property
    def claims_handled_count(self) -> int:
        return self.staff_profile.handled_claims.count()

    @property
    def claims_settled_count(self) -> int:
        return self.staff_profile.handled_claims.filter(status='SETTLED').count()

    @property
    def average_resolution_hours(self) -> float:
        settled = self.staff_profile.handled_claims.filter(status='SETTLED', settled_at__isnull=False)
        if not settled.exists():
            return 0.0
        total_seconds = sum((c.settled_at - c.created_at).total_seconds() for c in settled)
        return round(total_seconds / (3600.0 * settled.count()), 1)


class AssignmentStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    INACTIVE = 'INACTIVE', 'Inactive'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'


class StaffCustomerAssignment(AuditableModel):
    """
    Persistent relationship linking a Staff member to an assigned customer.
    Enforces that staff can only access customer records explicitly assigned to them.
    """
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_customer_assignments',
        help_text='Staff member assigned to this customer',
    )
    customer = models.ForeignKey(
        'customers.CustomerProfile',
        on_delete=models.CASCADE,
        related_name='staff_assignments',
        help_text='Assigned customer profile',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_created',
        help_text='Administrator who executed the assignment',
    )
    assigned_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        db_index=True,
    )
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assignment_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Staff-Customer Assignment'
        verbose_name_plural = 'Staff-Customer Assignments'
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer'],
                condition=models.Q(status='ACTIVE'),
                name='unique_active_staff_customer_assignment',
            )
        ]

    def __str__(self):
        return f"{self.staff.email} -> {self.customer.customer_code} ({self.status})"
