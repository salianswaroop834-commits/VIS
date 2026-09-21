from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.customers.models import CustomerProfile
from core.services import DataNormalizer, ServiceValidationError
from apps.audit.models import AuditAction
from apps.audit.services.audit_service import AuditService


class VehicleService:
    """
    Manages vehicle registry operations:
    - Input normalization (license plates, VIN/Chassis numbers)
    - Identity and valuation validation
    - Non-financial update restrictions during active policy coverage
    - Non-destructive vehicle deactivation/archiving
    - Non-repudiation audit logging
    """

    @classmethod
    def create_vehicle(cls, customer: CustomerProfile, data: Dict[str, Any]) -> Vehicle:
        """
        Validates, normalizes, and registers a vehicle asset.
        """
        raw_reg = data.get('registration_number', '')
        reg_number = DataNormalizer.normalize_registration_number(raw_reg)
        if not reg_number:
            raise ServiceValidationError("Vehicle registration plate number is required.")

        raw_chassis = data.get('chassis_number', '')
        chassis_number = DataNormalizer.normalize_vin_or_chassis(raw_chassis)
        if not chassis_number:
            raise ServiceValidationError("Chassis number / VIN is required.")

        # Check unique constraints
        if Vehicle.objects.filter(registration_number=reg_number).exists():
            raise ServiceValidationError(f"A vehicle with registration '{reg_number}' already exists in the system.")

        if Vehicle.objects.filter(chassis_number=chassis_number).exists():
            raise ServiceValidationError(f"A vehicle with VIN/Chassis '{chassis_number}' already exists in the system.")

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
            raise ServiceValidationError("Vehicle value must be a valid decimal amount.")

        if value <= Decimal('0'):
            raise ServiceValidationError("Insured Declared Value (IDV) must be greater than zero.")

        vehicle_type = data.get('vehicle_type', VehicleType.SEDAN)
        fuel_type = data.get('fuel_type', FuelType.PETROL)
        usage_type = data.get('usage_type', UsageType.PERSONAL)
        engine_num = DataNormalizer.normalize_text(data.get('engine_number', ''))

        vehicle = Vehicle.objects.create(
            customer=customer,
            registration_number=reg_number,
            chassis_number=chassis_number,
            make=make,
            model=model,
            manufacture_year=year,
            vehicle_type=vehicle_type,
            fuel_type=fuel_type,
            engine_number=engine_num,
            vehicle_value=value,
            usage_type=usage_type,
        )

        AuditService.log(
            action=AuditAction.VEHICLE_CREATED,
            target_entity='Vehicle',
            target_id=str(vehicle.pk),
            actor=customer.user,
            details={
                'registration_number': vehicle.registration_number,
                'make': vehicle.make,
                'model': vehicle.model,
                'vehicle_value': float(vehicle.vehicle_value),
            }
        )
        return vehicle

    @classmethod
    def update_vehicle_non_financial(cls, vehicle: Vehicle, data: Dict[str, Any]) -> Vehicle:
        """
        Updates non-financial attributes of an existing vehicle.
        If an active policy covers this vehicle, valuation and registration plate
        cannot be altered mid-term without a formal endorsement.
        """
        has_active_policy = vehicle.policies.filter(status='ACTIVE').exists()

        if has_active_policy:
            new_reg = DataNormalizer.normalize_registration_number(data.get('registration_number', ''))
            if new_reg and new_reg != vehicle.registration_number:
                raise ServiceValidationError(
                    "Cannot modify registration plate of a vehicle with an active policy mid-term."
                )

            new_val = data.get('vehicle_value')
            if new_val is not None and Decimal(str(new_val)) != vehicle.vehicle_value:
                raise ServiceValidationError(
                    "Vehicle valuation (IDV) is locked by an active policy. Financial changes require renewal."
                )

        # Apply permitted updates
        if 'engine_number' in data:
            vehicle.engine_number = DataNormalizer.normalize_text(data['engine_number'])
        if 'usage_type' in data and data['usage_type'] in UsageType.values:
            vehicle.usage_type = data['usage_type']
        if 'fuel_type' in data and data['fuel_type'] in FuelType.values:
            vehicle.fuel_type = data['fuel_type']

        vehicle.save()
        return vehicle

    @classmethod
    def update_vehicle(
        cls,
        vehicle: Vehicle,
        customer: CustomerProfile,
        data: Dict[str, Any],
        actor: Any = None,
    ) -> Vehicle:
        """
        Updates an existing vehicle asset.
        Enforces customer ownership and active-policy financial lock rules.
        """
        # Rule: Customer ownership check
        if vehicle.customer != customer:
            raise ServiceValidationError("Unauthorized: You may only edit vehicles registered to your account.")

        has_active_policy = vehicle.policies.filter(status='ACTIVE').exists()

        if has_active_policy:
            # Delegate to update_vehicle_non_financial which strictly blocks changes to reg plate & IDV
            cls.update_vehicle_non_financial(vehicle, data)
        else:
            # Full update permitted with normalization and validations
            if 'registration_number' in data:
                raw_reg = data.get('registration_number', '')
                reg_number = DataNormalizer.normalize_registration_number(raw_reg)
                if not reg_number:
                    raise ServiceValidationError("Vehicle registration plate number cannot be blank.")
                if Vehicle.objects.filter(registration_number=reg_number).exclude(pk=vehicle.pk).exists():
                    raise ServiceValidationError(f"A vehicle with registration '{reg_number}' already exists in the system.")
                vehicle.registration_number = reg_number

            if 'chassis_number' in data:
                raw_chassis = data.get('chassis_number', '')
                chassis_number = DataNormalizer.normalize_vin_or_chassis(raw_chassis)
                if not chassis_number:
                    raise ServiceValidationError("Chassis number / VIN cannot be blank.")
                if Vehicle.objects.filter(chassis_number=chassis_number).exclude(pk=vehicle.pk).exists():
                    raise ServiceValidationError(f"A vehicle with VIN/Chassis '{chassis_number}' already exists in the system.")
                vehicle.chassis_number = chassis_number

            if 'make' in data:
                make = DataNormalizer.normalize_text(data.get('make', ''))
                if not make:
                    raise ServiceValidationError("Vehicle make is required.")
                vehicle.make = make

            if 'model' in data:
                model = DataNormalizer.normalize_text(data.get('model', ''))
                if not model:
                    raise ServiceValidationError("Vehicle model is required.")
                vehicle.model = model

            if 'manufacture_year' in data:
                try:
                    year = int(data.get('manufacture_year', 0))
                except (ValueError, TypeError):
                    raise ServiceValidationError("Manufacture year must be a valid integer.")
                current_year = timezone.now().year
                if year < 1980 or year > current_year + 1:
                    raise ServiceValidationError(f"Manufacture year must be between 1980 and {current_year + 1}.")
                vehicle.manufacture_year = year

            if 'vehicle_value' in data:
                try:
                    value = Decimal(str(data.get('vehicle_value', '0')))
                except Exception:
                    raise ServiceValidationError("Vehicle value must be a valid decimal amount.")
                if value <= Decimal('0'):
                    raise ServiceValidationError("Insured Declared Value (IDV) must be greater than zero.")
                vehicle.vehicle_value = value

            if 'vehicle_type' in data and data['vehicle_type'] in VehicleType.values:
                vehicle.vehicle_type = data['vehicle_type']
            if 'fuel_type' in data and data['fuel_type'] in FuelType.values:
                vehicle.fuel_type = data['fuel_type']
            if 'usage_type' in data and data['usage_type'] in UsageType.values:
                vehicle.usage_type = data['usage_type']
            if 'engine_number' in data:
                vehicle.engine_number = DataNormalizer.normalize_text(data['engine_number'])

            vehicle.save()

        AuditService.log(
            action=AuditAction.VEHICLE_UPDATED,
            target_entity='Vehicle',
            target_id=str(vehicle.pk),
            actor=actor or customer.user,
            details={
                'registration_number': vehicle.registration_number,
                'vehicle_value': float(vehicle.vehicle_value),
                'has_active_policy': has_active_policy,
            }
        )
        return vehicle

    @classmethod
    def deactivate_vehicle(
        cls,
        vehicle: Vehicle,
        customer: CustomerProfile,
        actor: Any = None,
    ) -> Vehicle:
        """
        Deactivates / archives a customer's vehicle asset.
        Prohibits deactivation if an active insurance policy is currently binding.
        """
        if vehicle.customer != customer:
            raise ServiceValidationError("Unauthorized: You may only deactivate vehicles registered to your account.")

        if vehicle.policies.filter(status='ACTIVE').exists():
            raise ServiceValidationError(
                "Cannot deactivate vehicle: It is currently covered under an active insurance policy."
            )

        vehicle.is_active = False
        vehicle.save(update_fields=['is_active', 'updated_at'])

        AuditService.log(
            action=AuditAction.VEHICLE_DEACTIVATED,
            target_entity='Vehicle',
            target_id=str(vehicle.pk),
            actor=actor or customer.user,
            details={
                'registration_number': vehicle.registration_number,
                'make': vehicle.make,
                'model': vehicle.model,
            }
        )
        return vehicle

