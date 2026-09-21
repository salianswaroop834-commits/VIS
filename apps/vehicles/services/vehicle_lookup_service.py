from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import User
from apps.customers.models import CustomerProfile
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from integrations.rapidapi.vehicle.client import RapidApiVehicleProvider
from integrations.rapidapi.exceptions import (
    VehicleNotFoundError,
    InvalidRegistrationNumberError,
    RateLimitError,
    ProviderUnavailableError,
)
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService
from core.services import DataNormalizer, ServiceValidationError, NotificationService


class VehicleLookupService:
    """
    Two-Step Vehicle Registry Lookup and Confirmation Service:
    Step 1: Fetch normalized technical specifications from national registry without persisting.
    Step 2: Customer reviews, edits permitted fields, and explicitly confirms before database persistence.
    """

    @classmethod
    def lookup_vehicle(
        cls,
        registration_number: str,
        actor: Optional[User] = None,
        actor_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Step 1: Queries vehicle registry adapter and returns normalized preview structure.
        Does NOT persist record to database.
        """
        raw_reg = registration_number.strip().upper()
        clean_reg = DataNormalizer.normalize_registration_number(raw_reg)
        if not clean_reg:
            raise ServiceValidationError("Please enter a valid vehicle registration plate number.")

        if Vehicle.objects.filter(registration_number=clean_reg).exists():
            raise ServiceValidationError(f"Vehicle '{clean_reg}' is already registered in the system.")

        provider = RapidApiVehicleProvider()
        try:
            vehicle_data = provider.get_vehicle_details(clean_reg)
        except VehicleNotFoundError as e:
            raise ServiceValidationError(str(e))
        except InvalidRegistrationNumberError as e:
            raise ServiceValidationError(str(e))
        except (RateLimitError, ProviderUnavailableError) as e:
            raise ServiceValidationError(str(e))

        AuditService.log(
            action=AuditAction.VEHICLE_LOOKUP,
            target_entity='Vehicle',
            target_id=clean_reg,
            actor=actor,
            details={
                'registration_number': clean_reg,
                'make': vehicle_data.get('make'),
                'model': vehicle_data.get('model'),
            },
            ip_address=actor_ip,
        )

        vehicle_data['fetched_from_registry'] = True
        return vehicle_data

    @classmethod
    def verify_chassis(
        cls,
        registration_number: str,
        last_5_chassis: str,
        actor: Optional[User] = None,
        actor_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verifies the last 5 characters of a vehicle's chassis against the external registry.
        """
        clean_reg = DataNormalizer.normalize_registration_number(registration_number)
        clean_chassis = (last_5_chassis or '').strip().upper()
        if not clean_reg:
            raise ServiceValidationError("Vehicle registration plate number is required.")
        if len(clean_chassis) != 5 or not clean_chassis.isalnum():
            raise ServiceValidationError("Last 5 chassis characters must be exactly 5 alphanumeric characters.")

        provider = RapidApiVehicleProvider()
        try:
            result = provider.verify_chassis(clean_reg, clean_chassis)
        except (VehicleNotFoundError, InvalidRegistrationNumberError, RateLimitError, ProviderUnavailableError) as e:
            raise ServiceValidationError(str(e))

        AuditService.log(
            action=AuditAction.VEHICLE_LOOKUP,
            target_entity='Vehicle',
            target_id=clean_reg,
            actor=actor,
            is_success=result['verified'],
            details={
                'registration_number': clean_reg,
                'chassis_verified': result['verified'],
                'submitted_last_5': clean_chassis,
            },
            ip_address=actor_ip,
        )
        return result

    @classmethod
    @transaction.atomic
    def confirm_and_save_vehicle(
        cls,
        customer: CustomerProfile,
        data: Dict[str, Any],
        actor: Optional[User] = None,
        actor_ip: Optional[str] = None,
    ) -> Vehicle:
        """
        Step 2: Customer explicitly confirms fetched registry details and submits.
        Persists record only after explicit user confirmation.
        """
        reg_number = DataNormalizer.normalize_registration_number(data.get('registration_number', ''))
        if not reg_number:
            raise ServiceValidationError("Vehicle registration plate number is required.")

        if Vehicle.objects.filter(registration_number=reg_number).exists():
            raise ServiceValidationError(f"Vehicle '{reg_number}' already exists.")

        raw_chassis = data.get('chassis_number', '')
        chassis_number = DataNormalizer.normalize_vin_or_chassis(raw_chassis)
        if not chassis_number:
            raise ServiceValidationError("VIN / Chassis number is mandatory.")

        if Vehicle.objects.filter(chassis_number=chassis_number).exists():
            raise ServiceValidationError(f"A vehicle with VIN/Chassis '{chassis_number}' is already registered.")

        make = DataNormalizer.normalize_text(data.get('make', ''))
        model = DataNormalizer.normalize_text(data.get('model', ''))
        if not make or not model:
            raise ServiceValidationError("Vehicle make and model are required.")

        try:
            year = int(data.get('manufacture_year', 0))
        except (ValueError, TypeError):
            raise ServiceValidationError("Manufacture year must be a valid integer.")

        current_year = timezone.now().year
        if year < 1980 or year > current_year + 1:
            raise ServiceValidationError(f"Manufacture year must be between 1980 and {current_year + 1}.")

        try:
            value = Decimal(str(data.get('vehicle_value', '0')))
        except Exception:
            raise ServiceValidationError("Insured Declared Value (IDV) must be a valid amount.")

        if value <= Decimal('0'):
            raise ServiceValidationError("Vehicle IDV must be greater than zero.")

        # Map types with fallbacks
        v_type = data.get('vehicle_type', VehicleType.SEDAN)
        if v_type not in VehicleType.values:
            v_type = VehicleType.SEDAN

        f_type = data.get('fuel_type', FuelType.PETROL)
        if f_type not in FuelType.values:
            f_type = FuelType.PETROL

        u_type = data.get('usage_type', UsageType.PERSONAL)
        if u_type not in UsageType.values:
            u_type = UsageType.PERSONAL

        vehicle = Vehicle.objects.create(
            customer=customer,
            registration_number=reg_number,
            make=make,
            model=model,
            variant=DataNormalizer.normalize_text(data.get('variant', '')),
            vehicle_type=v_type,
            fuel_type=f_type,
            usage_type=u_type,
            manufacture_year=year,
            vehicle_value=value,
            chassis_number=chassis_number,
            engine_number=DataNormalizer.normalize_text(data.get('engine_number', '')),
            registration_state=DataNormalizer.normalize_text(data.get('registration_state', '')),
            registration_city=DataNormalizer.normalize_text(data.get('registration_city', '')),
            owner_name=DataNormalizer.normalize_text(data.get('owner_name', '')),
            fitness_upto=data.get('fitness_upto') or None,
            insurance_upto=data.get('insurance_upto') or None,
        )

        AuditService.log(
            action=AuditAction.VEHICLE_CREATED,
            target_entity='Vehicle',
            target_id=str(vehicle.pk),
            actor=actor or customer.user,
            details={
                'registration_number': vehicle.registration_number,
                'make': vehicle.make,
                'model': vehicle.model,
                'vehicle_value': float(vehicle.vehicle_value),
                'confirmed_by_user': True,
            },
            ip_address=actor_ip,
        )

        NotificationService.notify(
            recipient=customer.user,
            title="Vehicle Verified & Registered",
            message=f"Vehicle {vehicle.registration_number} ({vehicle.make} {vehicle.model}) has been verified and registered in your account.",
            notification_type='GENERAL',
            action_url='/customer/vehicles/',
        )

        return vehicle

