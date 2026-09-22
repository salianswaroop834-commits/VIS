from decimal import Decimal
from datetime import date, timedelta
import pytest
from django.db import IntegrityError
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile
from apps.vehicles.models import Vehicle, VehicleType
from apps.quotations.models import CoveragePlan, CoveragePlanCode, CoverageFeature, QuotationDraft
from apps.quotations.services.quotation_service import QuotationService
from apps.quotations.selectors import (
    get_active_coverage_plans,
    get_coverage_plan_by_code,
    get_customer_quotations,
    get_quotation_by_number,
)
from apps.policies.models import Policy, PolicyStatus
from apps.policies.selectors import (
    get_customer_policies,
    get_policy_by_number,
    get_policy_renewal_lineage,
    get_underwriter_portfolio,
)
from apps.claims.models import Claim, ClaimStatus
from apps.claims.selectors import (
    get_customer_claims,
    get_pending_claims_queue,
    get_handler_assigned_claims,
    get_claim_by_number,
)
from apps.vehicles.selectors import (
    get_customer_vehicles,
    get_vehicle_by_registration,
    get_vehicle_by_chassis,
)


@pytest.fixture
def domain_fixture(db):
    QuotationService.seed_default_plans()

    # Customer
    cust_user = User.objects.create_user(
        username='domain_cust',
        email='domain.cust@example.com',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    customer = CustomerProfile.objects.create(
        user=cust_user,
        customer_code='CUST-DOM-001',
    )

    # Underwriter
    uw_user = User.objects.create_user(
        username='domain_uw',
        email='domain.uw@example.com',
        role=UserRole.UNDERWRITER,
        password='password123',
    )
    underwriter = StaffProfile.objects.create(
        user=uw_user,
        staff_code='EMP-DOM-UW1',
        department='Underwriting',
    )

    # Claims Handler
    ch_user = User.objects.create_user(
        username='domain_ch',
        email='domain.ch@example.com',
        role=UserRole.CLAIMS_HANDLER,
        password='password123',
    )
    handler = StaffProfile.objects.create(
        user=ch_user,
        staff_code='EMP-DOM-CH1',
        department='Claims',
        max_claim_approval_limit=Decimal('25000.00'),
    )

    # Vehicle
    vehicle = Vehicle.objects.create(
        customer=customer,
        registration_number='NY99ZZ0001',
        vehicle_type=VehicleType.SEDAN,
        make='Toyota',
        model='Camry',
        manufacture_year=2023,
        chassis_number='4T1B11HK5PU123456',
        vehicle_value=Decimal('28000.00'),
    )

    # Plan
    plan = CoveragePlan.objects.get(plan_code=CoveragePlanCode.COMPREHENSIVE)

    # Policy
    today = date.today()
    policy = Policy.objects.create(
        policy_number='POL-2026-DOM01',
        customer=customer,
        vehicle=vehicle,
        coverage_plan=plan,
        underwriter=underwriter,
        start_date=today,
        end_date=today.replace(year=today.year + 1),
        premium_amount=Decimal('798.00'),
        deductible_amount=Decimal('1000.00'),
        status=PolicyStatus.ACTIVE,
    )

    return {
        'customer': customer,
        'underwriter': underwriter,
        'handler': handler,
        'vehicle': vehicle,
        'plan': plan,
        'policy': policy,
    }


@pytest.mark.django_db
class TestDatabaseDomainFoundation:

    def test_coverage_features_seeded_and_itemized(self, domain_fixture):
        features = CoverageFeature.objects.filter(plan__plan_code=CoveragePlanCode.COMPREHENSIVE)
        assert features.count() >= 5
        standard_features = features.filter(is_standard=True)
        assert standard_features.count() >= 4

        # Verify selectors
        plans = get_active_coverage_plans()
        assert plans.count() == 3
        comp = get_coverage_plan_by_code(CoveragePlanCode.COMPREHENSIVE)
        assert comp is not None
        assert comp.features.count() >= 5

    def test_quotation_draft_with_underwriter_relationship(self, domain_fixture):
        f = domain_fixture
        draft = QuotationService.create_quotation_draft(
            vehicle_value=Decimal('30000.00'),
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=f['customer'],
            vehicle=f['vehicle'],
            underwriter=f['underwriter'],
        )
        assert draft.underwriter == f['underwriter']
        assert draft.customer == f['customer']
        assert draft.vehicle == f['vehicle']

        # Selector tests
        quotes = get_customer_quotations(f['customer'])
        assert quotes.count() >= 1
        fetched = get_quotation_by_number(draft.quotation_number)
        assert fetched.pk == draft.pk

    def test_policy_date_check_constraint(self, domain_fixture):
        f = domain_fixture
        today = date.today()

        # Valid dates: end_date > start_date
        assert f['policy'].end_date > f['policy'].start_date

        # Invalid dates: end_date <= start_date must raise IntegrityError
        with pytest.raises(IntegrityError):
            Policy.objects.create(
                policy_number='POL-INVALID-DATES',
                customer=f['customer'],
                vehicle=f['vehicle'],
                coverage_plan=f['plan'],
                underwriter=f['underwriter'],
                start_date=today,
                end_date=today - timedelta(days=1),  # Inverted dates
                premium_amount=Decimal('500.00'),
                deductible_amount=Decimal('1000.00'),
                status=PolicyStatus.ACTIVE,
            )

    def test_claim_pending_null_handler_constraint(self, domain_fixture):
        f = domain_fixture
        # Valid: PENDING with handler=None
        claim = Claim.objects.create(
            claim_number='CLM-VALID-PENDING',
            policy=f['policy'],
            customer=f['customer'],
            handler=None,
            incident_date=timezone.now(),
            incident_location='Broadway & 5th Ave',
            incident_description='Minor bumper scrape in parking garage',
            estimated_loss_amount=Decimal('450.00'),
            status=ClaimStatus.PENDING,
        )
        assert claim.handler is None
        assert claim.status == ClaimStatus.PENDING

        # Invalid: PENDING with handler assigned must be blocked by DB constraint
        with pytest.raises(IntegrityError):
            Claim.objects.create(
                claim_number='CLM-INVALID-PENDING',
                policy=f['policy'],
                customer=f['customer'],
                handler=f['handler'],  # Not allowed while PENDING
                incident_date=timezone.now(),
                incident_location='Main St',
                incident_description='Violation test',
                estimated_loss_amount=Decimal('1000.00'),
                status=ClaimStatus.PENDING,
            )

    def test_policy_renewal_lineage_and_selectors(self, domain_fixture):
        f = domain_fixture
        from apps.policies.services.policy_service import PolicyService

        renewal = PolicyService.renew_policy(f['policy'], duration_years=1)
        assert renewal.previous_policy == f['policy']
        assert renewal.status == PolicyStatus.ACTIVE
        f['policy'].refresh_from_db()
        assert f['policy'].status == PolicyStatus.RENEWED

        lineage = get_policy_renewal_lineage(renewal)
        assert len(lineage) == 2
        assert lineage[0].pk == f['policy'].pk
        assert lineage[1].pk == renewal.pk

        # Selectors
        cust_policies = get_customer_policies(f['customer'])
        assert cust_policies.count() == 2
        active_policies = get_customer_policies(f['customer'], active_only=True)
        assert active_policies.count() == 1
        assert active_policies.first().pk == renewal.pk

        uw_portfolio = get_underwriter_portfolio(f['underwriter'])
        assert uw_portfolio.count() == 2

    def test_vehicle_and_claim_selectors(self, domain_fixture):
        f = domain_fixture
        # Vehicle selectors
        v_list = get_customer_vehicles(f['customer'])
        assert v_list.count() == 1
        by_reg = get_vehicle_by_registration('ny 99 zz 0001')
        assert by_reg.pk == f['vehicle'].pk
        by_vin = get_vehicle_by_chassis('4t1b11hk5pu123456')
        assert by_vin.pk == f['vehicle'].pk

        # Create a pending claim for customer
        claim = Claim.objects.create(
            claim_number='CLM-QUEUE-TEST-01',
            policy=f['policy'],
            customer=f['customer'],
            handler=None,
            incident_date=timezone.now(),
            incident_location='Main St',
            incident_description='Queue test incident',
            estimated_loss_amount=Decimal('500.00'),
            status=ClaimStatus.PENDING,
        )

        # Claims queue selector
        queue = get_pending_claims_queue()
        assert queue.filter(customer=f['customer']).exists()
        assert queue.filter(pk=claim.pk).exists()
