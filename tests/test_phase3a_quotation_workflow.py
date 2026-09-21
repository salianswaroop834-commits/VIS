from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile
from apps.vehicles.models import Vehicle, VehicleType
from apps.quotations.models import CoveragePlan, CoveragePlanCode, CoverageFeature, QuotationDraft
from apps.quotations.services.quotation_service import QuotationService
from apps.policies.models import Policy, PolicyStatus
from apps.policies.services.policy_service import PolicyService
from apps.audit.models import AuditLog, AuditAction
from core.services import ServiceValidationError


@pytest.fixture
def quote_workflow_data(db):
    QuotationService.seed_default_plans()

    # Customer 1 (Alice)
    alice_user = User.objects.create_user(
        username='alice_quote',
        email='alice.quote@example.com',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    alice_customer = CustomerProfile.objects.create(
        user=alice_user,
        customer_code='CUST-ALICE-01',
    )
    alice_vehicle = Vehicle.objects.create(
        customer=alice_customer,
        registration_number='DL01AA1111',
        vehicle_type=VehicleType.SEDAN,
        make='Hyundai',
        model='Verna',
        manufacture_year=2022,
        chassis_number='MALC1111AA2222BB',
        vehicle_value=Decimal('800000.00'),  # ₹8,00,000 IDV
    )

    # Customer 2 (Bob)
    bob_user = User.objects.create_user(
        username='bob_quote',
        email='bob.quote@example.com',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    bob_customer = CustomerProfile.objects.create(
        user=bob_user,
        customer_code='CUST-BOB-02',
    )
    bob_vehicle = Vehicle.objects.create(
        customer=bob_customer,
        registration_number='MH02BB2222',
        vehicle_type=VehicleType.SUV,
        make='Tata',
        model='Harrier',
        manufacture_year=2023,
        chassis_number='MAT62222BB3333CC',
        vehicle_value=Decimal('1500000.00'),  # ₹15,00,000 IDV
    )

    # Underwriter Staff
    uw_user = User.objects.create_user(
        username='uw_quote',
        email='uw.quote@nexisure.internal',
        role=UserRole.UNDERWRITER,
        password='password123',
    )
    uw_staff = StaffProfile.objects.create(
        user=uw_user,
        staff_code='EMP-UW-Q1',
        department='Underwriting',
    )

    # Administrator
    admin_user = User.objects.create_user(
        username='admin_quote',
        email='admin.quote@nexisure.internal',
        role=UserRole.ADMINISTRATOR,
        password='password123',
    )

    plan = CoveragePlan.objects.get(plan_code=CoveragePlanCode.COMPREHENSIVE)

    return {
        'alice_user': alice_user,
        'alice_customer': alice_customer,
        'alice_vehicle': alice_vehicle,
        'bob_user': bob_user,
        'bob_customer': bob_customer,
        'bob_vehicle': bob_vehicle,
        'uw_user': uw_user,
        'uw_staff': uw_staff,
        'admin_user': admin_user,
        'plan': plan,
    }


@pytest.mark.django_db
class TestPhase3AQuotationWorkflow:
    """
    Automated verification of Phase 3A requirements:
    1. Coverage plan browsing (active only, INR formatting, feature distinction)
    2. Customer quotation creation & server-side ownership validation
    3. Multi-year term discount and optional rider premium calculations
    4. Quotation detail view access control & RBAC isolation
    5. Quotation acceptance lifecycle: DRAFT -> ACCEPTED
    6. Expiry and duplicate acceptance prevention
    7. Quotation to policy conversion: ACCEPTED -> CONVERTED with locked financials
    8. Audit log verification
    9. UI smoke testing with INR (₹) representation
    """

    def test_customer_can_create_quotation_for_own_vehicle(self, quote_workflow_data):
        d = quote_workflow_data
        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
            actor=d['alice_user'],
        )

        assert draft.pk is not None
        assert draft.quotation_number.startswith('QTE-')
        assert draft.customer == d['alice_customer']
        assert draft.vehicle == d['alice_vehicle']
        assert draft.status == QuotationDraft.QuotationStatus.DRAFT
        assert draft.vehicle_value == Decimal('800000.00')

        # Comprehensive base rate: 2.850% -> 800000 * 0.0285 = 22,800.00
        assert draft.calculated_premium == Decimal('22800.00')
        assert draft.base_premium == Decimal('22800.00')

        # Verify audit log
        audit = AuditLog.objects.filter(
            target_entity='QuotationDraft',
            target_id=str(draft.pk),
            action=AuditAction.QUOTATION_CREATED,
        ).first()
        assert audit is not None
        assert audit.actor == d['alice_user']

    def test_customer_cannot_create_quotation_for_another_customers_vehicle(self, quote_workflow_data, client):
        d = quote_workflow_data

        # Service-level rejection
        with pytest.raises(ServiceValidationError, match="Vehicle does not belong to the authenticated customer"):
            QuotationService.create_quotation_draft(
                vehicle_value=Decimal('500000.00'),
                plan_code=CoveragePlanCode.COMPREHENSIVE,
                duration_years=1,
                customer=d['alice_customer'],
                vehicle=d['bob_vehicle'],  # Bob's vehicle assigned to Alice!
                actor=d['alice_user'],
            )

        # View-level security: Alice tries to post Bob's vehicle ID
        client.force_login(d['alice_user'])
        response = client.post(reverse('quotations:create'), {
            'vehicle_id': str(d['bob_vehicle'].id),
            'coverage_plan': CoveragePlanCode.COMPREHENSIVE,
            'duration_years': '1',
            'vehicle_value': '800000',
        }, follow=True)

        # Should redirect back to estimator with error message
        assert any("Security Error" in m.message or "does not belong" in m.message for m in response.context['messages'])
        assert QuotationDraft.objects.filter(customer=d['alice_customer'], vehicle=d['bob_vehicle']).count() == 0

    def test_active_coverage_plans_only(self, quote_workflow_data, client):
        # Create an inactive plan
        inactive_plan = CoveragePlan.objects.create(
            plan_code='DEPRECATED_TIER',
            name='Deprecated Legacy Tier',
            description='Should not be browsable',
            base_rate_percentage=Decimal('4.000'),
            is_active=False,
        )

        response = client.get(reverse('quotations:plans'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Comprehensive / Full Insurance' in content
        assert 'Deprecated Legacy Tier' not in content
        assert '₹' in content

    def test_inactive_plan_rejected_at_service_layer(self):
        with pytest.raises(ServiceValidationError, match="Invalid coverage plan code"):
            QuotationService.calculate_simulated_premium(
                vehicle_value=Decimal('500000.00'),
                plan_code='NON_EXISTENT_PLAN',
            )

    def test_premium_calculated_with_multi_year_and_riders(self, quote_workflow_data):
        d = quote_workflow_data
        # IDV: ₹10,00,000, Comprehensive (2.85%)
        # 1 Year Annual Base: 1000000 * 0.0285 = 28,500.00
        # 2 Years (5% discount): 28500 * 2 * 0.95 = 54,150.00
        # Optional Zero Dep rider (+₹45.00/yr): 45 * 2 = 90.00
        # Total = 54,240.00
        comp_plan = d['plan']
        rider = comp_plan.features.filter(is_standard=False).first()

        calc = QuotationService.calculate_simulated_premium(
            vehicle_value=Decimal('1000000.00'),
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=2,
            selected_feature_ids=[rider.id] if rider else [],
        )

        assert calc['base_premium'] == Decimal('54150.00')
        if rider:
            assert calc['addon_premium'] == rider.add_on_premium * 2
            assert calc['calculated_premium'] == Decimal('54150.00') + (rider.add_on_premium * 2)
        else:
            assert calc['calculated_premium'] == Decimal('54150.00')

    def test_quotation_owner_isolation(self, quote_workflow_data, client):
        d = quote_workflow_data
        # Alice creates a quotation
        alice_quote = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
            actor=d['alice_user'],
        )

        # Bob attempts to view Alice's quotation -> 403 Forbidden
        client.force_login(d['bob_user'])
        response = client.get(reverse('quotations:detail', kwargs={'pk': alice_quote.pk}))
        assert response.status_code == 403

        # Alice views her own quotation -> 200 OK
        client.force_login(d['alice_user'])
        response = client.get(reverse('quotations:detail', kwargs={'pk': alice_quote.pk}))
        assert response.status_code == 200
        assert alice_quote.quotation_number in response.content.decode('utf-8')

    def test_quotation_detail_access_by_underwriter_and_admin(self, quote_workflow_data, client):
        d = quote_workflow_data
        alice_quote = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )

        # Underwriter can access
        client.force_login(d['uw_user'])
        resp_uw = client.get(reverse('quotations:detail', kwargs={'pk': alice_quote.pk}))
        assert resp_uw.status_code == 200

        # Administrator can access
        client.force_login(d['admin_user'])
        resp_admin = client.get(reverse('quotations:detail', kwargs={'pk': alice_quote.pk}))
        assert resp_admin.status_code == 200

    def test_valid_quotation_can_be_accepted(self, quote_workflow_data):
        d = quote_workflow_data
        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )
        assert draft.status == QuotationDraft.QuotationStatus.DRAFT

        # Accept quotation
        accepted = QuotationService.accept_quotation(draft, actor=d['alice_user'])
        assert accepted.status == QuotationDraft.QuotationStatus.ACCEPTED

        # Verify audit log
        audit = AuditLog.objects.filter(
            target_entity='QuotationDraft',
            target_id=str(accepted.pk),
            action=AuditAction.QUOTATION_ACCEPTED,
        ).first()
        assert audit is not None
        assert audit.actor == d['alice_user']

    def test_expired_quotation_cannot_be_accepted(self, quote_workflow_data):
        d = quote_workflow_data
        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )
        # Manually expire the valid_until date
        draft.valid_until = timezone.now() - timedelta(days=1)
        draft.save(update_fields=['valid_until'])

        with pytest.raises(ServiceValidationError, match="This quotation has expired"):
            QuotationService.accept_quotation(draft, actor=d['alice_user'])

        draft.refresh_from_db()
        assert draft.status == QuotationDraft.QuotationStatus.EXPIRED

    def test_quotation_cannot_be_accepted_twice(self, quote_workflow_data):
        d = quote_workflow_data
        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )
        QuotationService.accept_quotation(draft, actor=d['alice_user'])

        with pytest.raises(ServiceValidationError, match="already been accepted"):
            QuotationService.accept_quotation(draft, actor=d['alice_user'])

    def test_accepted_quotation_converts_to_policy_with_locked_financials(self, quote_workflow_data):
        d = quote_workflow_data
        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=2,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )
        QuotationService.accept_quotation(draft, actor=d['alice_user'])

        # Issue policy from accepted quotation
        policy = PolicyService.issue_policy_from_quotation(draft)
        assert policy.pk is not None
        assert policy.status == PolicyStatus.ACTIVE
        assert policy.policy_number.startswith('POL-')

        # Financial lock verification
        assert policy.customer == d['alice_customer']
        assert policy.vehicle == d['alice_vehicle']
        assert policy.coverage_plan == draft.coverage_plan
        assert policy.premium_amount == draft.calculated_premium
        assert policy.deductible_amount == draft.deductible_amount
        assert policy.duration_years == draft.duration_years
        assert policy.end_date > policy.start_date

        # Quotation is marked CONVERTED
        draft.refresh_from_db()
        assert draft.status == QuotationDraft.QuotationStatus.CONVERTED

        # Cannot convert twice
        with pytest.raises(ServiceValidationError, match="already been converted"):
            PolicyService.issue_policy_from_quotation(draft)

    def test_inr_formatting_in_customer_views(self, quote_workflow_data, client):
        d = quote_workflow_data
        client.force_login(d['alice_user'])

        draft = QuotationService.create_quotation_draft(
            vehicle_value=d['alice_vehicle'].vehicle_value,
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            duration_years=1,
            customer=d['alice_customer'],
            vehicle=d['alice_vehicle'],
        )

        # Detail view renders INR symbol ₹ and calculated premium
        resp = client.get(reverse('quotations:detail', kwargs={'pk': draft.pk}))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert '₹' in content
        assert '22,800.00' in content or '22800' in content

        # Quotations list view
        resp_list = client.get(reverse('quotations:list'))
        assert resp_list.status_code == 200
        assert draft.quotation_number in resp_list.content.decode('utf-8')
        assert '₹' in resp_list.content.decode('utf-8')

        # Convert view renders INR symbol ₹
        resp_convert = client.get(reverse('quotations:convert', kwargs={'pk': draft.pk}))
        assert resp_convert.status_code == 200
        assert '₹' in resp_convert.content.decode('utf-8')
        assert 'SIMULATED' in resp_convert.content.decode('utf-8')
