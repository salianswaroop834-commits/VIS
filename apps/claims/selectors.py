from typing import Optional
from django.db.models import QuerySet
from apps.claims.models import Claim, ClaimStatus
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile


def get_customer_claims(customer: CustomerProfile) -> QuerySet[Claim]:
    """
    Retrieves all claims filed by a customer profile.
    Ensures strict customer data isolation.
    """
    return Claim.objects.filter(customer=customer).select_related(
        'policy__vehicle', 'policy__coverage_plan', 'handler__user'
    ).order_by('-created_at')


def get_pending_claims_queue() -> QuerySet[Claim]:
    """
    Shared unassigned claims queue (handler_id = NULL, status = PENDING).
    Visible to all authorized claims handlers.
    """
    return Claim.objects.filter(
        status=ClaimStatus.PENDING,
        handler__isnull=True,
    ).select_related(
        'customer__user', 'policy__vehicle', 'policy__coverage_plan'
    ).order_by('created_at')


def get_handler_assigned_claims(
    handler: StaffProfile,
    status: Optional[str] = None,
) -> QuerySet[Claim]:
    """
    Retrieves claims currently assigned to a specific claims handler.
    """
    qs = Claim.objects.filter(handler=handler).select_related(
        'customer__user', 'policy__vehicle', 'policy__coverage_plan'
    ).order_by('-updated_at')

    if status:
        qs = qs.filter(status=status)

    return qs


def get_claim_by_number(claim_number: str) -> Optional[Claim]:
    """Retrieves a single claim with documents and events pre-fetched."""
    return Claim.objects.filter(claim_number=claim_number.strip().upper()).select_related(
        'customer__user', 'policy__vehicle', 'policy__coverage_plan', 'handler__user'
    ).prefetch_related('documents', 'events').first()
