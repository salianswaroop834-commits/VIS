from typing import Optional
from django.db.models import QuerySet
from service_requests.models import ServiceRequest, ServiceRequestStatus
from customers.models import CustomerProfile


def get_customer_service_requests(customer: CustomerProfile) -> QuerySet[ServiceRequest]:
    """
    Retrieves all service requests initiated by a specific customer.
    Enforces customer data isolation.
    """
    return ServiceRequest.objects.filter(customer=customer).select_related(
        'policy__vehicle', 'assigned_staff'
    ).order_by('-created_at')


def get_staff_service_requests(status: Optional[str] = None) -> QuerySet[ServiceRequest]:
    """
    Retrieves service requests for staff processing, optionally filtered by status.
    """
    qs = ServiceRequest.objects.all().select_related(
        'customer__user', 'policy__vehicle', 'assigned_staff'
    ).order_by('-created_at')

    if status and status in ServiceRequestStatus.values:
        qs = qs.filter(status=status)

    return qs


def get_service_request_by_number(request_number: str) -> Optional[ServiceRequest]:
    """
    Retrieves a single service request by its unique tracking number.
    """
    return ServiceRequest.objects.filter(
        request_number=request_number.strip().upper()
    ).select_related('customer__user', 'policy__vehicle', 'assigned_staff').first()
