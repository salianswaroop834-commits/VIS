from decimal import Decimal
from django.db import models
from core.models import AuditableModel
from customers.models import CustomerProfile
from vehicles.models import Vehicle
from staff.models import StaffProfile


class CoveragePlanCode(models.TextChoices):
    THIRD_PARTY = 'THIRD_PARTY', 'Third-Party Liability Only'
    COMPREHENSIVE = 'COMPREHENSIVE', 'Comprehensive / Full Insurance'
    ZERO_DEP_PREMIUM = 'ZERO_DEP_PREMIUM', 'Zero Depreciation Comprehensive'


class CoveragePlan(AuditableModel):
    """
    Standard vehicle insurance plan offerings with defined coverages and deductibles.
    """
    plan_code = models.CharField(
        max_length=50,
        unique=True,
        choices=CoveragePlanCode.choices,
        default=CoveragePlanCode.COMPREHENSIVE,
    )
    name = models.CharField(max_length=100)
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    base_rate_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        help_text='Annual premium rate as percentage of vehicle IDV (e.g. 2.850%)',
    )
    standard_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    includes_own_damage = models.BooleanField(default=True)
    includes_third_party = models.BooleanField(default=True)
    includes_roadside_assistance = models.BooleanField(default=False)
    includes_engine_protection = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Coverage Plan'
        verbose_name_plural = 'Coverage Plans'

    def __str__(self):
        return f"{self.name} ({self.get_plan_code_display()})"


class CoverageFeature(AuditableModel):
    """
    Itemized feature or add-on rider associated with a CoveragePlan.
    Supports plan comparison, feature highlights, and optional endorsement add-ons.
    """
    plan = models.ForeignKey(
        CoveragePlan,
        on_delete=models.CASCADE,
        related_name='features',
    )
    feature_code = models.CharField(max_length=50, db_index=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_standard = models.BooleanField(
        default=True,
        help_text='True if included as standard; False if optional add-on rider'
    )
    add_on_premium = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Additional premium if optional rider',
    )

    class Meta:
        verbose_name = 'Coverage Feature'
        verbose_name_plural = 'Coverage Features'
        unique_together = ('plan', 'feature_code')
        ordering = ['plan', 'title']

    def __str__(self):
        type_str = 'Standard' if self.is_standard else f"+₹{self.add_on_premium}"
        return f"{self.plan.name} - {self.title} ({type_str})"


class QuotationDraft(AuditableModel):
    """
    Quotation draft entity.
    Allows prospective or existing customers to compare coverages,
    calculate simulated premiums, and review options prior to purchase.
    """
    class QuotationStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACCEPTED = 'ACCEPTED', 'Accepted by Customer'
        EXPIRED = 'EXPIRED', 'Expired'
        CONVERTED = 'CONVERTED', 'Converted to Policy'

    quotation_number = models.CharField(max_length=40, unique=True, db_index=True)
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations',
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations',
    )
    coverage_plan = models.ForeignKey(
        CoveragePlan,
        on_delete=models.PROTECT,
        related_name='quotations',
    )
    underwriter = models.ForeignKey(
        StaffProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotations',
        help_text='Underwriter who prepared or reviewed this quote',
    )
    vehicle_value = models.DecimalField(max_digits=12, decimal_places=2, help_text='Insured Declared Value (IDV) in INR')
    duration_years = models.PositiveIntegerField(default=1, choices=[(1, '1 Year'), (2, '2 Years'), (3, '3 Years')])
    base_premium = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Base plan premium before optional riders in INR',
    )
    addon_premium = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Total premium for selected optional add-on riders in INR',
    )
    calculated_premium = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Total calculated premium in INR (Base + Add-ons)',
    )
    deductible_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Compulsory policy deductible in INR')
    selected_features = models.ManyToManyField(
        CoverageFeature,
        blank=True,
        related_name='quotations',
        help_text='Itemized features and optional riders included in this quotation',
    )
    status = models.CharField(
        max_length=20,
        choices=QuotationStatus.choices,
        default=QuotationStatus.DRAFT,
        db_index=True,
    )
    valid_until = models.DateTimeField()

    class Meta:
        verbose_name = 'Quotation Draft'
        verbose_name_plural = 'Quotation Drafts'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            orig = QuotationDraft.objects.filter(pk=self.pk).values(
                'status', 'calculated_premium', 'base_premium', 'deductible_amount', 'vehicle_value'
            ).first()
            if orig and orig['status'] in (self.QuotationStatus.ACCEPTED, self.QuotationStatus.CONVERTED):
                from core.services import ServiceValidationError
                if (orig['calculated_premium'] != self.calculated_premium or
                    orig['base_premium'] != self.base_premium or
                    orig['deductible_amount'] != self.deductible_amount or
                    orig['vehicle_value'] != self.vehicle_value):
                    raise ServiceValidationError(
                        f"Cannot modify financial fields of quotation in '{orig['status']}' status."
                    )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quotation_number} - {self.coverage_plan.name} (₹{self.calculated_premium})"


# Domain alias
Quotation = QuotationDraft
