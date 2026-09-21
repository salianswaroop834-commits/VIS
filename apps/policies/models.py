from decimal import Decimal
from django.db import models
from django.conf import settings
from core.models import AuditableModel
from apps.customers.models import CustomerProfile
from apps.vehicles.models import Vehicle
from apps.quotations.models import CoveragePlan
from apps.staff.models import StaffProfile


class PolicyStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    LAPSED = 'LAPSED', 'Lapsed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    EXPIRED = 'EXPIRED', 'Expired'
    RENEWED = 'RENEWED', 'Renewed'


class PolicyQuerySet(models.QuerySet):
    def _filter_or_exclude(self, negate, args, kwargs):
        new_kwargs = {}
        for k, v in kwargs.items():
            if k == 'underwriter':
                new_kwargs['assigned_staff'] = v
            elif k.startswith('underwriter__'):
                new_kwargs['assigned_staff' + k[11:]] = v
            else:
                new_kwargs[k] = v
        return super()._filter_or_exclude(negate, args, new_kwargs)

    def select_related(self, *fields):
        new_fields = []
        for f in fields:
            if f == 'underwriter':
                new_fields.append('assigned_staff')
            elif isinstance(f, str) and f.startswith('underwriter__'):
                new_fields.append('assigned_staff' + f[11:])
            else:
                new_fields.append(f)
        return super().select_related(*new_fields)


class PolicyManager(models.Manager.from_queryset(PolicyQuerySet)):
    pass


class Policy(AuditableModel):
    """
    Core insurance contract entity representing an active, lapsed, or cancelled policy.
    Financial and contract fields are strictly immutable once issued.
    """
    objects = PolicyManager()
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
    assigned_staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='underwritten_policies',
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_policies',
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
    cancellation_reason = models.TextField(blank=True)
    cancellation_date = models.DateField(null=True, blank=True)
    renewal_date = models.DateField(null=True, blank=True)

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

    @property
    def underwriter(self):
        return self.assigned_staff

    @underwriter.setter
    def underwriter(self, value):
        self.assigned_staff = value

    def save(self, *args, **kwargs):
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            uf = set(kwargs['update_fields'])
            if 'underwriter' in uf:
                uf.remove('underwriter')
                uf.add('assigned_staff')
                kwargs['update_fields'] = list(uf)
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


class Addon(AuditableModel):
    """
    Rider / endorsement definition for policies.
    """
    addon_name = models.CharField(max_length=100)
    addon_code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)
    addon_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Addon'
        verbose_name_plural = 'Addons'
        ordering = ['addon_name']

    def __str__(self):
        return f"{self.addon_name} ({self.addon_code}) - ₹{self.addon_cost}"


class PolicyAddon(AuditableModel):
    """
    Explicit junction table binding purchased addons to a policy with historical pricing.
    """
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='policy_addons',
    )
    addon = models.ForeignKey(
        Addon,
        on_delete=models.PROTECT,
        related_name='policy_instances',
    )
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Policy Addon'
        verbose_name_plural = 'Policy Addons'
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'addon'],
                name='unique_policy_addon',
            )
        ]

    def __str__(self):
        return f"{self.policy.policy_number} - {self.addon.addon_name} (₹{self.price_at_purchase})"
