from typing import Optional, Any
from django.db.models import QuerySet
from apps.quotations.models import CoveragePlan, CoverageFeature, QuotationDraft
from apps.customers.models import CustomerProfile


def get_active_coverage_plans() -> QuerySet[CoveragePlan]:
    """Retrieves all active coverage plans with pre-fetched itemized features."""
    return CoveragePlan.objects.filter(is_active=True).prefetch_related('features').order_by('base_rate_percentage')


def get_coverage_plan_by_code(plan_code: str) -> Optional[CoveragePlan]:
    """Retrieves a single coverage plan by its code with features."""
    return CoveragePlan.objects.filter(plan_code=plan_code, is_active=True).prefetch_related('features').first()


def get_customer_quotations(
    customer: CustomerProfile,
    status: Optional[str] = None,
) -> QuerySet[QuotationDraft]:
    """
    Retrieves all quotation drafts for a customer profile.
    Ensures strict customer data isolation.
    """
    qs = QuotationDraft.objects.filter(customer=customer).select_related(
        'coverage_plan', 'vehicle', 'underwriter'
    ).prefetch_related('selected_features').order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    return qs


def get_quotation_by_number(quotation_number: str) -> Optional[QuotationDraft]:
    """Retrieves a quotation draft by its number with features pre-fetched."""
    return QuotationDraft.objects.filter(quotation_number=quotation_number.strip().upper()).select_related(
        'customer__user', 'vehicle', 'coverage_plan', 'underwriter'
    ).prefetch_related('selected_features', 'coverage_plan__features').first()


def get_quotation_by_id(pk: Any) -> Optional[QuotationDraft]:
    """Retrieves a quotation draft by its UUID primary key with features pre-fetched."""
    return QuotationDraft.objects.filter(pk=pk).select_related(
        'customer__user', 'vehicle', 'coverage_plan', 'underwriter'
    ).prefetch_related('selected_features', 'coverage_plan__features').first()
