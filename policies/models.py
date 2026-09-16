from django.db import models
from core.models import AuditableModel
from customers.models import CustomerProfile
from vehicles.models import Vehicle
from quotations.models import CoveragePlan
from staff.models import StaffProfile


class PolicyStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    EXPIRED = 'EXPIRED', 'Expired'
    CANCELLED = 'CANCELLED', 'Cancelled'
    RENEWED = 'RENEWED', 'Renewed'


class Policy(AuditableModel):
    """
    Vehicle Insurance Policy Contract entity.
    Maintains financial lock, temporal validity, and immutable renewal lineage.
    """
    policy_number = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        help_text='Unique policy identifier (e.g. POL-2026-100234)',
    )
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.PROTECT,
        related_name='policies',
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name='policies',
    )
    coverage_plan = models.ForeignKey(
        CoveragePlan,
        on_delete=models.PROTECT,
        related_name='policies',
    )
    underwriter = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='underwritten_policies',
    )
    premium_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Locked premium amount for this policy term',
    )
    deductible_amount = models.DecimalField(max_digits=10, decimal_places=2)
    duration_years = models.PositiveIntegerField(
        default=1,
        choices=[(1, '1 Year'), (2, '2 Years'), (3, '3 Years')],
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=PolicyStatus.choices,
        default=PolicyStatus.ACTIVE,
        db_index=True,
    )
    previous_policy = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewal_history',
        help_text='Lineage tracking for renewal history without mutating past records',
    )

    class Meta:
        verbose_name = 'Policy'
        verbose_name_plural = 'Policies'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F('start_date')),
                name='chk_policy_dates',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            orig = Policy.objects.filter(pk=self.pk).values('premium_amount', 'deductible_amount', 'policy_number').first()
            if orig:
                from core.services import ServiceValidationError
                if orig['premium_amount'] != self.premium_amount:
                    raise ServiceValidationError("Cannot modify immutable financial field 'premium_amount' after policy issuance.")
                if orig['deductible_amount'] != self.deductible_amount:
                    raise ServiceValidationError("Cannot modify immutable financial field 'deductible_amount' after policy issuance.")
                if orig['policy_number'] != self.policy_number:
                    raise ServiceValidationError("Cannot modify policy contract identifier 'policy_number' after issuance.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.policy_number} - {self.vehicle.registration_number} ({self.status})"
