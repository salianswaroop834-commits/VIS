from typing import List, Optional
from django.db.models import QuerySet
from policies.models import Policy, PolicyStatus
from customers.models import CustomerProfile
from staff.models import StaffProfile


def get_customer_policies(
    customer: CustomerProfile,
    active_only: bool = False,
) -> QuerySet[Policy]:
    """
    Retrieves all policies owned by a customer profile.
    Ensures strict customer data isolation.
    """
    qs = Policy.objects.filter(customer=customer).select_related(
        'vehicle', 'coverage_plan', 'underwriter'
    ).order_by('-created_at')

    if active_only:
        qs = qs.filter(status=PolicyStatus.ACTIVE)

    return qs


def get_policy_by_number(policy_number: str) -> Optional[Policy]:
    """Retrieves a single policy by its canonical policy number."""
    return Policy.objects.filter(policy_number=policy_number.strip().upper()).select_related(
        'customer__user', 'vehicle', 'coverage_plan', 'underwriter__user', 'previous_policy'
    ).first()


def get_policy_renewal_lineage(policy: Policy) -> List[Policy]:
    """
    Walks backward through historical policy renewal chain without mutating records.
    Returns list of policies starting from original issuance up to current renewal.
    """
    chain = [policy]
    curr = policy
    while curr.previous_policy:
        chain.insert(0, curr.previous_policy)
        curr = curr.previous_policy
    return chain


def get_underwriter_portfolio(
    underwriter: StaffProfile,
    status: Optional[str] = None,
) -> QuerySet[Policy]:
    """Retrieves policies assigned to an underwriter's portfolio."""
    qs = Policy.objects.filter(underwriter=underwriter).select_related(
        'customer__user', 'vehicle', 'coverage_plan'
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    return qs
