import re
from decimal import Decimal
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile, KYCVerification, KYCStatus
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.vehicles.data.synthetic_dataset import SYNTHETIC_USERS


class Command(BaseCommand):
    help = "Seeds 15 canonical Indian customer users and their 38 mapped vehicles with complete technical and KYC attributes."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding 15 Canonical Users and 38 Mapped Vehicles..."))

        users_created = 0
        vehicles_created = 0

        with transaction.atomic():
            for u_data in SYNTHETIC_USERS:
                username = u_data["email"].split("@")[0]
                user, created = User.objects.get_or_create(
                    email=u_data["email"],
                    defaults={
                        "username": username,
                        "first_name": u_data["first_name"],
                        "last_name": u_data["last_name"],
                        "role": UserRole.USER,
                        "phone_number": u_data["phone_number"],
                        "phone_verified": True,
                        "email_verified": True,
                        "is_staff": False,
                        "is_active": True,
                    }
                )
                if not created:
                    user.first_name = u_data["first_name"]
                    user.last_name = u_data["last_name"]
                    user.phone_number = u_data["phone_number"]
                    user.phone_verified = True
                    user.email_verified = True
                    user.role = UserRole.USER
                    user.save()

                user.set_password("DemoCustomer@2026")
                user.save()
                users_created += 1

                # Customer Profile
                profile, p_created = CustomerProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "customer_code": u_data["id_code"],
                        "driving_license_number": u_data["driving_license_number"],
                        "address_line": u_data["address_line"],
                        "city": u_data["city"],
                        "state": u_data["state"],
                        "postal_code": u_data["postal_code"],
                        "is_identity_verified": True,
                        "is_active": True,
                    }
                )
                if not p_created:
                    profile.customer_code = u_data["id_code"]
                    profile.driving_license_number = u_data["driving_license_number"]
                    profile.address_line = u_data["address_line"]
                    profile.city = u_data["city"]
                    profile.state = u_data["state"]
                    profile.postal_code = u_data["postal_code"]
                    profile.is_identity_verified = True
                    profile.save()

                # KYC Verification Record
                pan = u_data["pan_number"]
                phone = u_data["phone_number"]
                masked_pan = f"{pan[:5]}****{pan[-1]}"
                masked_phone = f"******{phone[-4:]}"
                
                KYCVerification.objects.get_or_create(
                    user=user,
                    verification_type="PAN",
                    defaults={
                        "document_number_masked": masked_pan,
                        "verified_phone_masked": masked_phone,
                        "status": KYCStatus.VERIFIED,
                        "verified_at": timezone.now(),
                    }
                )

                # Vehicles mapped to this Customer
                for v_data in u_data["vehicles"]:
                    v_type = getattr(VehicleType, v_data["vehicle_type"], VehicleType.SUV)
                    f_type = getattr(FuelType, v_data["fuel_type"], FuelType.PETROL)

                    veh, v_created = Vehicle.objects.get_or_create(
                        registration_number=v_data["registration_number"],
                        defaults={
                            "customer": profile,
                            "make": v_data["make"],
                            "model": v_data["model"],
                            "variant": v_data["variant"],
                            "vehicle_type": v_type,
                            "fuel_type": f_type,
                            "usage_type": UsageType.PERSONAL,
                            "manufacture_year": v_data["manufacture_year"],
                            "registration_date": v_data["registration_date"],
                            "engine_number": v_data["engine_number"],
                            "chassis_number": v_data["chassis_number"],
                            "fitness_upto": v_data["fitness_upto"],
                            "insurance_upto": v_data["insurance_upto"],
                            "vehicle_value": Decimal(v_data["vehicle_value"]),
                            "registration_state": v_data["registration_state"],
                            "registration_city": v_data["registration_city"],
                            "is_active": True,
                        }
                    )
                    if not v_created:
                        veh.customer = profile
                        veh.make = v_data["make"]
                        veh.model = v_data["model"]
                        veh.variant = v_data["variant"]
                        veh.vehicle_type = v_type
                        veh.fuel_type = f_type
                        veh.vehicle_value = Decimal(v_data["vehicle_value"])
                        veh.registration_state = v_data["registration_state"]
                        veh.registration_city = v_data["registration_city"]
                        veh.save()

                    vehicles_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {users_created} Users and {vehicles_created} Mapped Vehicles!"
        ))
