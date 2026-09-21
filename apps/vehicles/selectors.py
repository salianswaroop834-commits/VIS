from typing import Optional
from django.db.models import QuerySet
from apps.vehicles.models import Vehicle
from apps.customers.models import CustomerProfile
from core.services import DataNormalizer


def get_customer_vehicles(
    customer: CustomerProfile,
    active_only: bool = True,
) -> QuerySet[Vehicle]:
    """
    Retrieves all vehicle assets owned by a customer profile.
    Ensures strict customer data isolation.
    """
    qs = Vehicle.objects.filter(customer=customer).order_by('-created_at')
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_vehicle_by_registration(registration_number: str) -> Optional[Vehicle]:
    """Retrieves a vehicle by its normalized registration plate."""
    normalized = DataNormalizer.normalize_registration_number(registration_number)
    return Vehicle.objects.filter(registration_number=normalized).select_related(
        'customer__user'
    ).first()


def get_vehicle_by_chassis(chassis_number: str) -> Optional[Vehicle]:
    """Retrieves a vehicle by its normalized chassis number / VIN."""
    normalized = DataNormalizer.normalize_vin_or_chassis(chassis_number)
    return Vehicle.objects.filter(chassis_number=normalized).select_related(
        'customer__user'
    ).first()


def get_vehicle_by_id(vehicle_id) -> Optional[Vehicle]:
    """Retrieves a vehicle by its primary key UUID."""
    return Vehicle.objects.filter(id=vehicle_id).select_related(
        'customer__user'
    ).prefetch_related('policies__coverage_plan', 'quotations__coverage_plan').first()


def get_customer_vehicle_by_id(customer: CustomerProfile, vehicle_id) -> Optional[Vehicle]:
    """Retrieves a vehicle strictly scoped to the owner customer profile."""
    return Vehicle.objects.filter(id=vehicle_id, customer=customer).select_related(
        'customer__user'
    ).prefetch_related('policies__coverage_plan', 'quotations__coverage_plan').first()


