from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import UserRole
from customers.models import CustomerProfile
from customers.services.customer_service import CustomerService
from vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from vehicles.services.vehicle_service import VehicleService
from quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from quotations.services.quotation_service import QuotationService
from policies.models import Policy, PolicyStatus
from policies.services.policy_service import PolicyService, add_years_to_date
from core.services import ServiceValidationError

User = get_user_model()


@pytest.fixture
def test_customer_user():
    user = User.objects.create_user(
        username='cust_test',
        email='cust.test@example.com',
        password='Password123!',
        role=UserRole.CUSTOMER,
    )
    profile = CustomerProfile.objects.create(
        user=user,
        customer_code='CUST-TEST-01',
    )
    return user, profile


@pytest.fixture
def test_underwriter_user():
    from staff.models import StaffProfile
    user = User.objects.create_user(
        username='uw_tester',
        email='uw.tester@example.com',
        password='Password123!',
        role=UserRole.UNDERWRITER,
    )
    profile = StaffProfile.objects.create(
        user=user,
        staff_code='UW-999',
        department='Underwriting',
    )
    return user, profile


@pytest.mark.django_db
class TestPhase3CrudAndBusinessRules:
    """
    Automated verification of Phase 3 requirements:
    1. Coverage plan seeding and multi-year premium calculation formulas
    2. Vehicle registration, normalization, and update restrictions under active policy
    3. Policy issuance from quotation draft with financial locking and end-date arithmetic
    4. Immutable policy renewal with historical lineage and status progression
    5. Underwriter customer registration and search workflows
    """

    def test_coverage_plans_seeding_and_premium_formula(self):
        plans = QuotationService.seed_default_plans()
        assert len(plans) == 3

        # Value: $25,000, Comprehensive Plan (rate: 2.85%)
        # 1 Year: 25000 * 0.0285 = 712.50
        c1 = QuotationService.calculate_simulated_premium(
            vehicle_value=Decimal('25000.00'),
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
        )
        assert c1['calculated_premium'] == Decimal('712.50')
        assert c1['discount_percentage'] == Decimal('0.00')

        # 2 Years (5% multi-year discount): 712.50 * 2 * 0.95 = 1353.75
        c2 = QuotationService.calculate_simulated_premium(
            vehicle_value=Decimal('25000.00'),
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=2,
        )
        assert c2['calculated_premium'] == Decimal('1353.75')
        assert c2['discount_percentage'] == Decimal('5.00')

        # 3 Years (10% multi-year discount): 712.50 * 3 * 0.90 = 1923.75
        c3 = QuotationService.calculate_simulated_premium(
            vehicle_value=Decimal('25000.00'),
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=3,
        )
        assert c3['calculated_premium'] == Decimal('1923.75')
        assert c3['discount_percentage'] == Decimal('10.00')

        # Invalid vehicle values must be rejected
        with pytest.raises(ServiceValidationError):
            QuotationService.calculate_simulated_premium(Decimal('0'), CoveragePlanCode.COMPREHENSIVE)

    def test_vehicle_creation_and_normalization(self, test_customer_user):
        _, customer = test_customer_user
        vehicle_data = {
            'registration_number': '  wa-02-ab 4040  ',
            'chassis_number': '  1hgc-v1f32na-998811  ',
            'make': '  Toyota ',
            'model': ' RAV4  ',
            'manufacture_year': 2023,
            'vehicle_value': '32000.00',
            'vehicle_type': VehicleType.SUV,
            'fuel_type': FuelType.HYBRID,
            'usage_type': UsageType.PERSONAL,
        }

        vehicle = VehicleService.create_vehicle(customer, vehicle_data)
        assert vehicle.registration_number == 'WA02AB4040'
        assert vehicle.chassis_number == '1HGCV1F32NA998811'
        assert vehicle.make == 'Toyota'
        assert vehicle.model == 'RAV4'
        assert vehicle.vehicle_value == Decimal('32000.00')

        # Duplicate registration plate rejected
        with pytest.raises(ServiceValidationError) as exc:
            VehicleService.create_vehicle(customer, vehicle_data)
        assert "already exists in the system" in str(exc.value)

    def test_vehicle_financial_lock_under_active_policy(self, test_customer_user):
        _, customer = test_customer_user
        vehicle = VehicleService.create_vehicle(customer, {
            'registration_number': 'DL05XY1001',
            'chassis_number': '2HGFA16578H551201',
            'make': 'Honda',
            'model': 'Civic',
            'manufacture_year': 2021,
            'vehicle_value': '22000.00',
        })

        # Permitted non-financial updates prior to policy
        VehicleService.update_vehicle_non_financial(vehicle, {
            'engine_number': 'ENG-7721',
            'usage_type': UsageType.COMMERCIAL,
        })
        vehicle.refresh_from_db()
        assert vehicle.engine_number == 'ENG-7721'
        assert vehicle.usage_type == UsageType.COMMERCIAL

        # Create active policy covering this vehicle
        QuotationService.seed_default_plans()
        draft = QuotationService.create_quotation_draft(
            vehicle_value=vehicle.vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=customer,
            vehicle=vehicle,
        )
        policy = PolicyService.issue_policy_from_quotation(draft)
        assert policy.status == PolicyStatus.ACTIVE

        # Attempting to modify IDV or license plate during active policy must be blocked
        with pytest.raises(ServiceValidationError) as exc:
            VehicleService.update_vehicle_non_financial(vehicle, {'vehicle_value': '28000.00'})
        assert "locked by an active policy" in str(exc.value)

        with pytest.raises(ServiceValidationError) as exc:
            VehicleService.update_vehicle_non_financial(vehicle, {'registration_number': 'DL05XY9999'})
        assert "Cannot modify registration plate" in str(exc.value)

    def test_policy_issuance_and_end_date_arithmetic(self, test_customer_user):
        _, customer = test_customer_user
        vehicle = VehicleService.create_vehicle(customer, {
            'registration_number': 'NY99ZZ1234',
            'chassis_number': '3HGFA16578H991202',
            'make': 'Ford',
            'model': 'F-150',
            'manufacture_year': 2022,
            'vehicle_value': '45000.00',
        })

        start = date(2026, 10, 15)
        # End date for 1, 2, and 3 years
        assert add_years_to_date(start, 1) == date(2027, 10, 15)
        assert add_years_to_date(start, 2) == date(2028, 10, 15)
        assert add_years_to_date(start, 3) == date(2029, 10, 15)

        # Leap year boundary test: Feb 29 2024 + 1 year -> Feb 28 2025
        leap_start = date(2024, 2, 29)
        assert add_years_to_date(leap_start, 1) == date(2025, 2, 28)

        draft = QuotationService.create_quotation_draft(
            vehicle_value=vehicle.vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=2,
            customer=customer,
            vehicle=vehicle,
        )

        policy = PolicyService.issue_policy_from_quotation(draft, start_date=start)
        assert policy.policy_number.startswith('POL-2026-')
        assert policy.start_date == date(2026, 10, 15)
        assert policy.end_date == date(2028, 10, 15)
        assert policy.duration_years == 2
        assert policy.premium_amount == draft.calculated_premium
        assert policy.status == PolicyStatus.ACTIVE

        # Converted quotation cannot be reused
        draft.refresh_from_db()
        assert draft.status == QuotationDraft.QuotationStatus.CONVERTED
        with pytest.raises(ServiceValidationError):
            PolicyService.issue_policy_from_quotation(draft)

    def test_non_mutating_policy_renewal_lineage(self, test_customer_user):
        _, customer = test_customer_user
        vehicle = VehicleService.create_vehicle(customer, {
            'registration_number': 'CA44QQ8822',
            'chassis_number': '4HGFA16578H882203',
            'make': 'Subaru',
            'model': 'Outback',
            'manufacture_year': 2023,
            'vehicle_value': '30000.00',
        })

        start = date(2026, 5, 1)
        draft = QuotationService.create_quotation_draft(
            vehicle_value=vehicle.vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=customer,
            vehicle=vehicle,
        )
        old_policy = PolicyService.issue_policy_from_quotation(draft, start_date=start)
        assert old_policy.status == PolicyStatus.ACTIVE
        assert old_policy.end_date == date(2027, 5, 1)

        # Renew policy for 1 year
        renewed_policy = PolicyService.renew_policy(
            existing_policy=old_policy,
            duration_years=1,
        )

        # Verify new policy identity and dates
        assert renewed_policy.pk != old_policy.pk
        assert renewed_policy.policy_number != old_policy.policy_number
        assert renewed_policy.start_date == date(2027, 5, 2)
        assert renewed_policy.end_date == date(2028, 5, 2)
        assert renewed_policy.status == PolicyStatus.ACTIVE
        assert renewed_policy.previous_policy == old_policy

        # Verify old policy updated to RENEWED
        old_policy.refresh_from_db()
        assert old_policy.status == PolicyStatus.RENEWED

    def test_policy_search_by_number_and_registration(self, test_customer_user):
        _, customer = test_customer_user
        vehicle = VehicleService.create_vehicle(customer, {
            'registration_number': 'TX77MM3311',
            'chassis_number': '5HGFA16578H331104',
            'make': 'Mazda',
            'model': 'CX-5',
            'manufacture_year': 2022,
            'vehicle_value': '27000.00',
        })
        draft = QuotationService.create_quotation_draft(
            vehicle_value=vehicle.vehicle_value,
            plan_code=CoveragePlanCode.THIRD_PARTY,
            duration_years=1,
            customer=customer,
            vehicle=vehicle,
        )
        policy = PolicyService.issue_policy_from_quotation(draft)

        # Search by exact registration
        results1 = PolicyService.search_policies('TX77MM3311')
        assert policy in results1

        # Search by formatted plate with spaces
        results2 = PolicyService.search_policies('tx 77 mm 3311')
        assert policy in results2

        # Search by policy number prefix
        results3 = PolicyService.search_policies(policy.policy_number[:12])
        assert policy in results3

    def test_underwriter_customer_search_and_onboarding(self, test_underwriter_user):
        _, underwriter = test_underwriter_user

        customer_data = {
            'email': 'onboarded.driver@example.com',
            'first_name': 'Michael',
            'last_name': 'Chang',
            'phone_number': '+1 (555) 019-9944',
            'driving_license_number': 'DL-WA-88123',
            'city': 'Tacoma',
            'postal_code': '98402',
        }

        profile = CustomerService.register_customer_for_underwriting(customer_data, underwriter=underwriter)
        assert profile.user.email == 'onboarded.driver@example.com'
        assert profile.user.phone_number == '+15550199944'
        assert profile.customer_code.startswith('CUST-')

        # Search by phone
        search_phone = CustomerService.search_customers_by_identifier('5550199944')
        assert profile in search_phone

        # Search by code
        search_code = CustomerService.search_customers_by_identifier(profile.customer_code)
        assert profile in search_code
