import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from apps.policies.models import Policy, PolicyStatus
from apps.claims.models import Claim, ClaimStatus
from apps.claims.services.claim_service import ClaimService
from apps.service_requests.models import ServiceRequest, ServiceRequestType, ServiceRequestStatus
from apps.payments.services.payment_service import PaymentService
from core.services import ServiceValidationError


@pytest.mark.django_db
class TestPhase12IntegrationAndSecurity:
    """
    Phase 12: Complete End-to-End Product Integration & Security Audit.
    - End-to-end customer workflow (Quotation -> Payment -> Policy -> Claim -> Servicing)
    - End-to-end underwriter and claims handler workflows
    - Strict IDOR prevention across customer assets
    - Immutable financial contract fields
    - Consistent INR presentation
    """

    @pytest.fixture
    def setup_system(self):
        # 1. Coverage plan
        plan, _ = CoveragePlan.objects.get_or_create(
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            defaults={
                'name': 'Comprehensive Gold',
                'base_rate_percentage': Decimal('3.25'),
                'standard_deductible': Decimal('1500.00'),
            }
        )

        # 2. Customers
        user_cust_a = User.objects.create_user(
            username='cust_integration_a',
            email='alice.integ@nexisure.test',
            first_name='Alice',
            last_name='Integrator',
            role=UserRole.CUSTOMER,
        )
        profile_a = CustomerProfile.objects.create(
            user=user_cust_a,
            customer_code='CUST-INT-A',
            date_of_birth=date(1991, 5, 20),
            address_line='100 Tech Boulevard',
            city='Bengaluru',
            postal_code='560001',
        )

        user_cust_b = User.objects.create_user(
            username='cust_integration_b',
            email='bob.integ@nexisure.test',
            first_name='Bob',
            last_name='Integrator',
            role=UserRole.CUSTOMER,
        )
        profile_b = CustomerProfile.objects.create(
            user=user_cust_b,
            customer_code='CUST-INT-B',
            date_of_birth=date(1989, 9, 14),
            address_line='200 Harbor Road',
            city='Mumbai',
            postal_code='400001',
        )

        # 3. Staff members
        user_uw = User.objects.create_user(
            username='uw_integ',
            email='uw.integ@nexisure.test',
            first_name='Uma',
            last_name='Underwriter',
            role=UserRole.UNDERWRITER,
            is_staff=True,
        )
        staff_uw = StaffProfile.objects.create(
            user=user_uw,
            staff_code='UW-INT-01',
            department='Underwriting',
        )

        user_ch = User.objects.create_user(
            username='ch_integ',
            email='ch.integ@nexisure.test',
            first_name='Charlie',
            last_name='Handler',
            role=UserRole.CLAIMS_HANDLER,
            is_staff=True,
        )
        staff_ch = StaffProfile.objects.create(
            user=user_ch,
            staff_code='CH-INT-01',
            department='Claims',
            max_claim_approval_limit=Decimal('50000.00'),
        )

        return {
            'plan': plan,
            'cust_a': user_cust_a,
            'cust_b': user_cust_b,
            'uw': user_uw,
            'ch': user_ch,
            'staff_uw': staff_uw,
            'staff_ch': staff_ch,
        }

    def test_customer_end_to_end_journey(self, client, setup_system):
        """
        Comprehensive customer flow:
        Register vehicle -> generate quote -> simulated payment -> policy issued -> file claim -> service request
        """
        cust = setup_system['cust_a']
        client.force_login(cust)
        plan = setup_system['plan']

        # 1. Register vehicle
        vehicle = Vehicle.objects.create(
            customer=cust.customer_profile,
            registration_number='KA05AB1234',
            make='Maruti Suzuki',
            model='Swift',
            manufacture_year=2022,
            vehicle_type=VehicleType.HATCHBACK,
            fuel_type=FuelType.PETROL,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('650000.00'),
            chassis_number='CHASSIS-INT-1234',
        )
        assert vehicle.id is not None

        # 2. Generate quotation draft
        quotation = QuotationDraft.objects.create(
            quotation_number='QTE-INT-001',
            customer=cust.customer_profile,
            coverage_plan=plan,
            vehicle=vehicle,
            vehicle_value=vehicle.vehicle_value,
            duration_years=1,
            base_premium=Decimal('21125.00'),
            calculated_premium=Decimal('21125.00'),
            deductible_amount=plan.standard_deductible,
            valid_until=timezone.now() + timedelta(days=30),
        )
        assert quotation.status == QuotationDraft.QuotationStatus.DRAFT

        # 3. Customer accepts and pays via simulated gateway
        payment = PaymentService.process_simulated_payment(
            amount=quotation.calculated_premium,
            card_number='4532000000080001',
            expiry='12/28',
            cvv='123',
            quotation=quotation,
            user=cust,
        )
        assert payment.is_successful is True
        assert payment.policy is not None
        issued_policy = payment.policy
        assert issued_policy.status == PolicyStatus.ACTIVE
        assert issued_policy.premium_amount == Decimal('21125.00')

        # 4. View Issued Policy Detail (assert INR presentation)
        url_pol = reverse('policies:detail', args=[issued_policy.id])
        resp_pol = client.get(url_pol)
        assert resp_pol.status_code == 200
        content_pol = resp_pol.content.decode('utf-8')
        assert issued_policy.policy_number in content_pol
        assert '₹' in content_pol

        # 5. File a claim
        claim = ClaimService.file_claim(
            customer=cust.customer_profile,
            policy=issued_policy,
            incident_date=timezone.now(),
            incident_location='MG Road, Bengaluru',
            incident_description='Minor collision in city traffic',
            estimated_loss_amount=Decimal('15000.00'),
        )
        assert claim.status == ClaimStatus.PENDING
        assert claim.handler is None  # Shared queue

        # 6. Create a service request
        sr = ServiceRequest.objects.create(
            request_number='SR-INT-001',
            customer=cust.customer_profile,
            policy=issued_policy,
            request_type=ServiceRequestType.ADDRESS_UPDATE,
            title='Update contact phone number',
            description='Updated primary contact number to +91 9876543210',
            status=ServiceRequestStatus.SUBMITTED,
        )
        assert sr.id is not None

        # 7. Customer dashboard reflects all assets
        resp_dash = client.get(reverse('customers:dashboard'))
        assert resp_dash.status_code == 200
        content_dash = resp_dash.content.decode('utf-8')
        assert issued_policy.policy_number in content_dash
        assert claim.claim_number in content_dash

    def test_claims_handler_adjudication_flow(self, client, setup_system):
        """
        Claims handler workflow:
        Inspect shared queue -> Self-assign -> Review -> Human approval within limit
        """
        ch_user = setup_system['ch']
        staff_ch = setup_system['staff_ch']
        cust = setup_system['cust_a']
        plan = setup_system['plan']

        # Setup active policy and pending claim
        vehicle = Vehicle.objects.create(
            customer=cust.customer_profile,
            registration_number='KA01CH5555',
            make='Honda',
            model='City',
            manufacture_year=2021,
            vehicle_type=VehicleType.SEDAN,
            fuel_type=FuelType.PETROL,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('900000.00'),
        )
        policy = Policy.objects.create(
            policy_number='POL-INT-CH01',
            customer=cust.customer_profile,
            vehicle=vehicle,
            coverage_plan=plan,
            premium_amount=Decimal('25000.00'),
            deductible_amount=Decimal('1500.00'),
            duration_years=1,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=335),
            status=PolicyStatus.ACTIVE,
        )
        claim = ClaimService.file_claim(
            customer=cust.customer_profile,
            policy=policy,
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='Koramangala, Bengaluru',
            incident_description='Rear light damaged',
            estimated_loss_amount=Decimal('8500.00'),
        )

        client.force_login(ch_user)

        # 1. Claims queue view
        resp_q = client.get(reverse('claims:queue'))
        assert resp_q.status_code == 200
        assert claim.claim_number in resp_q.content.decode('utf-8')

        # 2. Self-assignment
        assigned_claim = ClaimService.self_assign_claim(claim, handler=staff_ch)
        assert assigned_claim.status == ClaimStatus.IN_REVIEW
        assert assigned_claim.handler == staff_ch

        # 3. Human decision: Approve claim
        settled_claim = ClaimService.approve_claim(
            claim=assigned_claim,
            handler=staff_ch,
            settlement_amount=Decimal('7500.00'),
            notes='Surveyor approved repair quotation minus deductible.',
        )
        assert settled_claim.status == ClaimStatus.APPROVED
        assert settled_claim.settlement_amount == Decimal('7500.00')

    def test_idor_protection_across_customers(self, client, setup_system):
        """Customer B cannot view or manipulate Customer A's policies, claims, or vehicles."""
        cust_a = setup_system['cust_a']
        cust_b = setup_system['cust_b']
        plan = setup_system['plan']

        vehicle_a = Vehicle.objects.create(
            customer=cust_a.customer_profile,
            registration_number='KA03IDOR01',
            make='Tata',
            model='Nexon',
            manufacture_year=2023,
            vehicle_type=VehicleType.SUV,
            fuel_type=FuelType.ELECTRIC,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('1500000.00'),
        )
        policy_a = Policy.objects.create(
            policy_number='POL-INT-IDOR01',
            customer=cust_a.customer_profile,
            vehicle=vehicle_a,
            coverage_plan=plan,
            premium_amount=Decimal('35000.00'),
            deductible_amount=Decimal('2000.00'),
            duration_years=1,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=355),
            status=PolicyStatus.ACTIVE,
        )
        claim_a = ClaimService.file_claim(
            customer=cust_a.customer_profile,
            policy=policy_a,
            incident_date=timezone.now() - timedelta(days=3),
            incident_location='Indiranagar',
            incident_description='Minor side door scratch',
            estimated_loss_amount=Decimal('5000.00'),
        )

        # Login as Customer B
        client.force_login(cust_b)

        # Attempt to access Alice's policy detail -> 403 or 404
        resp_pol = client.get(reverse('policies:detail', args=[policy_a.id]))
        assert resp_pol.status_code in [403, 404]

        # Attempt to access Alice's claim detail -> 403 or 404
        resp_clm = client.get(reverse('claims:detail', args=[claim_a.id]))
        assert resp_clm.status_code in [403, 404]

    def test_immutable_financial_fields_enforcement(self, setup_system):
        """Locked policy cannot have its premium or deductible mutated after issuance."""
        cust = setup_system['cust_a']
        plan = setup_system['plan']

        vehicle = Vehicle.objects.create(
            customer=cust.customer_profile,
            registration_number='KA04LOCK99',
            make='Hyundai',
            model='i20',
            manufacture_year=2022,
            vehicle_type=VehicleType.HATCHBACK,
            fuel_type=FuelType.PETROL,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('700000.00'),
        )
        policy = Policy.objects.create(
            policy_number='POL-INT-LOCK01',
            customer=cust.customer_profile,
            vehicle=vehicle,
            coverage_plan=plan,
            premium_amount=Decimal('22000.00'),
            deductible_amount=Decimal('1500.00'),
            duration_years=1,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            status=PolicyStatus.ACTIVE,
        )

        # Direct mutation attempt
        policy.premium_amount = Decimal('10000.00')
        with pytest.raises(ServiceValidationError) as exc:
            policy.save()
        assert "Cannot modify immutable financial field" in str(exc.value)
