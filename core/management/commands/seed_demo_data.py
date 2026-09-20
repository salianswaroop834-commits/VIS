import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffProfile
from vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from quotations.services.quotation_service import QuotationService
from policies.models import Policy, PolicyStatus
from claims.models import Claim, ClaimStatus, ClaimEvent, ClaimEventType
from service_requests.models import ServiceRequest, ServiceRequestType, ServiceRequestStatus
from audit.services.audit_service import AuditService
from rag.services.rag_service import RagService
from predictions.models import ModelVersion, ModelLifecycleStatus


class Command(BaseCommand):
    help = "Seeds clearly synthetic academic demonstration data for presentation, testing, and viva."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing Nexisure synthetic demo seed..."))

        with transaction.atomic():
            # 1. Seed default coverage plans and knowledge corpus
            QuotationService.seed_default_plans()
            RagService.ingest_corpus()
            self.stdout.write(self.style.SUCCESS("  [OK] Coverage plans & knowledge corpus ingested."))

            # 2. Demo Users & Profiles
            # Admin
            admin_user, _ = User.objects.get_or_create(
                username='demo_admin',
                defaults={
                    'email': 'admin@nexisure.test',
                    'first_name': 'Eleanor',
                    'last_name': 'Vance',
                    'role': UserRole.ADMINISTRATOR,
                    'is_staff': True,
                    'is_superuser': True,
                    'email_verified': True,
                }
            )
            admin_user.set_password('DemoAdmin@2026')
            admin_user.save()
            admin_staff, _ = StaffProfile.objects.get_or_create(
                user=admin_user,
                defaults={
                    'staff_code': 'STF-ADM-001',
                    'department': 'Executive Administration',
                    'max_claim_approval_limit': Decimal('1000000.00'),
                }
            )

            # Underwriter
            uw_user, _ = User.objects.get_or_create(
                username='demo_underwriter',
                defaults={
                    'email': 'underwriter@nexisure.test',
                    'first_name': 'Sarah',
                    'last_name': 'Connor',
                    'role': UserRole.UNDERWRITER,
                    'is_staff': True,
                    'email_verified': True,
                }
            )
            uw_user.set_password('DemoStaff@2026')
            uw_user.save()
            uw_staff, _ = StaffProfile.objects.get_or_create(
                user=uw_user,
                defaults={
                    'staff_code': 'STF-UW-001',
                    'department': 'Vehicle Underwriting',
                    'max_claim_approval_limit': Decimal('0.00'),
                }
            )

            # Claims Handler
            ch_user, _ = User.objects.get_or_create(
                username='demo_handler',
                defaults={
                    'email': 'handler@nexisure.test',
                    'first_name': 'Marcus',
                    'last_name': 'Brody',
                    'role': UserRole.CLAIMS_HANDLER,
                    'is_staff': True,
                    'email_verified': True,
                }
            )
            ch_user.set_password('DemoStaff@2026')
            ch_user.save()
            ch_staff, _ = StaffProfile.objects.get_or_create(
                user=ch_user,
                defaults={
                    'staff_code': 'STF-CH-001',
                    'department': 'Claims Adjudication',
                    'max_claim_approval_limit': Decimal('50000.00'),
                }
            )

            # Customer
            cust_user, _ = User.objects.get_or_create(
                username='demo_customer',
                defaults={
                    'email': 'customer@nexisure.test',
                    'first_name': 'Aarav',
                    'last_name': 'Sharma',
                    'role': UserRole.CUSTOMER,
                    'email_verified': True,
                }
            )
            cust_user.set_password('DemoCust@2026')
            cust_user.save()
            cust_profile, _ = CustomerProfile.objects.get_or_create(
                user=cust_user,
                defaults={
                    'customer_code': 'CUST-DEMO-01',
                    'date_of_birth': date(1990, 8, 15),
                    'driving_license_number': 'DL-KA01-20150001234',
                    'address_line': '402 Sunrise Residency, Indiranagar',
                    'city': 'Bengaluru',
                    'state': 'Karnataka',
                    'postal_code': '560038',
                    'is_identity_verified': True,
                }
            )
            self.stdout.write(self.style.SUCCESS("  [OK] Demo accounts created (Admin, Underwriter, Claims Handler, Customer)."))

            # 3. Customer Vehicles
            plan_comp = CoveragePlan.objects.get(plan_code=CoveragePlanCode.COMPREHENSIVE)
            plan_zero = CoveragePlan.objects.get(plan_code=CoveragePlanCode.ZERO_DEP_PREMIUM)

            veh1, _ = Vehicle.objects.get_or_create(
                registration_number='KA01DEMO01',
                defaults={
                    'customer': cust_profile,
                    'make': 'Hyundai',
                    'model': 'Creta SX (O)',
                    'manufacture_year': 2023,
                    'vehicle_type': VehicleType.SUV,
                    'fuel_type': FuelType.PETROL,
                    'usage_type': UsageType.PERSONAL,
                    'vehicle_value': Decimal('1450000.00'),
                    'chassis_number': 'CHAS-DEMO-CRETA-01',
                }
            )

            veh2, _ = Vehicle.objects.get_or_create(
                registration_number='KA03DEMO02',
                defaults={
                    'customer': cust_profile,
                    'make': 'Tata',
                    'model': 'Nexon EV Empowered',
                    'manufacture_year': 2024,
                    'vehicle_type': VehicleType.SUV,
                    'fuel_type': FuelType.ELECTRIC,
                    'usage_type': UsageType.PERSONAL,
                    'vehicle_value': Decimal('1750000.00'),
                    'chassis_number': 'CHAS-DEMO-NEXON-02',
                }
            )

            # 4. Quotation Drafts
            q1, _ = QuotationDraft.objects.get_or_create(
                quotation_number='QTE-2026-DEMO01',
                defaults={
                    'customer': cust_profile,
                    'vehicle': veh2,
                    'coverage_plan': plan_zero,
                    'vehicle_value': veh2.vehicle_value,
                    'duration_years': 1,
                    'base_premium': Decimal('42000.00'),
                    'addon_premium': Decimal('3500.00'),
                    'calculated_premium': Decimal('45500.00'),
                    'deductible_amount': Decimal('2000.00'),
                    'valid_until': timezone.now() + timedelta(days=25),
                    'status': QuotationDraft.QuotationStatus.DRAFT,
                }
            )

            # 5. Active Policy
            pol1, _ = Policy.objects.get_or_create(
                policy_number='POL-2026-DEMO01',
                defaults={
                    'customer': cust_profile,
                    'vehicle': veh1,
                    'coverage_plan': plan_comp,
                    'underwriter': uw_staff,
                    'premium_amount': Decimal('32500.00'),
                    'deductible_amount': Decimal('1500.00'),
                    'duration_years': 1,
                    'start_date': date.today() - timedelta(days=60),
                    'end_date': date.today() + timedelta(days=305),
                    'status': PolicyStatus.ACTIVE,
                }
            )

            # 6. Claims in various states
            clm_pending, _ = Claim.objects.get_or_create(
                claim_number='CLM-2026-DEMO-PEND',
                defaults={
                    'policy': pol1,
                    'customer': cust_profile,
                    'incident_date': timezone.now() - timedelta(days=3),
                    'incident_location': 'Outer Ring Road, Marathahalli',
                    'incident_description': 'Side mirror sheared off by passing auto-rickshaw during peak traffic.',
                    'estimated_loss_amount': Decimal('4500.00'),
                    'status': ClaimStatus.PENDING,
                    'handler': None,  # Shared queue
                }
            )

            clm_review, _ = Claim.objects.get_or_create(
                claim_number='CLM-2026-DEMO-REV',
                defaults={
                    'policy': pol1,
                    'customer': cust_profile,
                    'incident_date': timezone.now() - timedelta(days=7),
                    'incident_location': 'Koramangala 5th Block',
                    'incident_description': 'Front fender dent from reversing into high curb in parking lot.',
                    'estimated_loss_amount': Decimal('18000.00'),
                    'status': ClaimStatus.IN_REVIEW,
                    'handler': ch_staff,
                }
            )

            # 7. Service Requests
            sr1, _ = ServiceRequest.objects.get_or_create(
                request_number='SR-2026-DEMO01',
                defaults={
                    'customer': cust_profile,
                    'policy': pol1,
                    'request_type': ServiceRequestType.ADDRESS_UPDATE,
                    'title': 'Correspondence Address Update',
                    'description': 'Updated flat number and added landmark: Near BDA Complex, Indiranagar.',
                    'status': ServiceRequestStatus.SUBMITTED,
                }
            )

            # 7b. Insurance Add-on Riders
            from policies.models import Addon, PolicyAddon
            addons_data = [
                ('ROADSIDE_ASSIST', 'Roadside Assistance', '24/7 towing, battery jumpstart, flat-tire, and fuel dispatch services.', Decimal('1200.00')),
                ('ENGINE_PROTECT', 'Engine Protect', 'Covers engine damage due to water ingression, lubricant leakage, and hydro-lock.', Decimal('2500.00')),
                ('CONSUMABLES', 'Consumables Cover', 'Covers nuts, bolts, lubricants, AC gas, and other consumables during repair.', Decimal('900.00')),
                ('RETURN_TO_INVOICE', 'Return to Invoice', 'Compensates the full invoice value of the vehicle in case of total loss or theft.', Decimal('3200.00')),
                ('NCB_PROTECT', 'NCB Protect', 'Preserves your No-Claim Bonus discount even after filing a claim.', Decimal('1500.00')),
                ('KEY_PROTECT', 'Key Protect', 'Covers the cost of replacing, reprogramming, or re-configuring lost vehicle keys and locks.', Decimal('800.00')),
                ('PASSENGER_COVER', 'Passenger Cover', 'Provides personal accident cover for occupants and named passengers.', Decimal('1000.00')),
                ('TYRE_PROTECT', 'Tyre Protect', 'Covers tyre and rim damage from road hazards, curb impacts, and punctures.', Decimal('1100.00')),
            ]
            seeded_addons = []
            for code, name, desc, cost in addons_data:
                addon_obj, _ = Addon.objects.get_or_create(
                    addon_code=code,
                    defaults={
                        'addon_name': name,
                        'description': desc,
                        'addon_cost': cost,
                    }
                )
                seeded_addons.append(addon_obj)

            # Attach sample addons to the demo policy
            for addon_obj in seeded_addons[:3]:  # Roadside, Engine Protect, Consumables
                PolicyAddon.objects.get_or_create(
                    policy=pol1,
                    addon=addon_obj,
                    defaults={'price_at_purchase': addon_obj.addon_cost}
                )
            self.stdout.write(self.style.SUCCESS(f"  [OK] {len(seeded_addons)} insurance add-on riders seeded."))

            # 7c. Demo Notifications
            from core.models import Notification, NotificationType
            Notification.objects.get_or_create(
                recipient=cust_user,
                title='Welcome to Nexisure!',
                defaults={
                    'message': 'Your account has been created. Explore your dashboard, view your policies, and manage your vehicles.',
                    'notification_type': NotificationType.GENERAL,
                }
            )
            Notification.objects.get_or_create(
                recipient=cust_user,
                title=f'Claim {clm_review.claim_number} Under Review',
                defaults={
                    'message': f'Your claim {clm_review.claim_number} is now under review by our claims team.',
                    'notification_type': NotificationType.CLAIM_STATUS,
                }
            )

            # 8. MLOps Model Version Records
            m1, _ = ModelVersion.objects.get_or_create(
                model_name='ClaimOccurrenceClassifier',
                version='1.0.0',
                defaults={
                    'algorithm_name': 'GradientBoostingClassifier',
                    'feature_version': 'v1.2',
                    'status': ModelLifecycleStatus.ACTIVE,
                    'deployment_status': 'PRODUCTION',
                    'is_active_for_inference': True,
                    'evaluation_metrics': {'accuracy': 0.884, 'precision': 0.812, 'recall': 0.776, 'f1_score': 0.793, 'roc_auc': 0.865},
                    'training_dataset_version': 'dataset_synthetic_v1_7500',
                }
            )

            m2, _ = ModelVersion.objects.get_or_create(
                model_name='ClaimSeverityRegressor',
                version='1.0.0',
                defaults={
                    'algorithm_name': 'RandomForestRegressor',
                    'feature_version': 'v1.2',
                    'status': ModelLifecycleStatus.ACTIVE,
                    'deployment_status': 'PRODUCTION',
                    'is_active_for_inference': True,
                    'evaluation_metrics': {'mae': 412.50, 'rmse': 685.20, 'r2': 0.764},
                    'training_dataset_version': 'dataset_synthetic_v1_7500',
                }
            )

            # 9. Audit Event
            AuditService.log(
                action='SYSTEM_DEMO_SEEDED',
                target_entity='Platform',
                target_id='DEMO-SEED-2026',
                actor=admin_user,
                details={'description': 'Academic demo seed successfully executed.'}
            )

        self.stdout.write(self.style.SUCCESS("\n========================================================"))
        self.stdout.write(self.style.SUCCESS("  NEXISURE DEMO SEED COMPLETED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("========================================================"))
        self.stdout.write("  Demo Credentials (Academic / Evaluation):")
        self.stdout.write("  * Administrator:    admin@nexisure.test      / DemoAdmin@2026")
        self.stdout.write("  * Underwriter:      underwriter@nexisure.test / DemoStaff@2026")
        self.stdout.write("  * Claims Handler:   handler@nexisure.test     / DemoStaff@2026")
        self.stdout.write("  * Customer:         customer@nexisure.test    / DemoCust@2026")
        self.stdout.write("--------------------------------------------------------")
        self.stdout.write("  Seed Summary:")
        self.stdout.write(f"  * Registered Vehicles:  {Vehicle.objects.count()}")
        self.stdout.write(f"  * Active Policies:      {Policy.objects.filter(status='ACTIVE').count()}")
        self.stdout.write(f"  * Pending Claims Queue: {Claim.objects.filter(status='PENDING').count()}")
        self.stdout.write(f"  * Service Requests:     {ServiceRequest.objects.count()}")
        self.stdout.write("========================================================\n")
