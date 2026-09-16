import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffProfile
from vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from vehicles.services.vehicle_service import VehicleService
from quotations.models import CoveragePlan, CoveragePlanCode
from policies.models import Policy, PolicyStatus
from policies.services.policy_service import PolicyService
from policies.selectors import get_policy_renewal_lineage
from service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from audit.models import AuditLog, AuditAction
from core.services import ServiceValidationError


@pytest.mark.django_db
class TestPhase3CPolicyLifecycle:
    """
    Comprehensive test suite for Phase 3C: Policy Lifecycle Completion.
    Verifies:
    1. Policy detail access
    2. Ownership isolation
    3. Certificate generation
    4. Certificate authorization
    5. Endorsement request
    6. Endorsement validation
    7. Endorsement approval
    8. Endorsement rejection
    9. Financial immutability
    10. Cancellation
    11. Invalid cancellation
    12. Renewal
    13. Renewal lineage
    14. Duplicate renewal prevention
    15. Audit events
    16. RBAC
    17. CSRF / state-changing endpoints
    18. INR currency presentation
    """

    @pytest.fixture(autouse=True)
    def setup_entities(self):
        # Customer A (Alice)
        self.user_a = User.objects.create_user(
            username='alice_policy',
            email='alice.policy@example.com',
            role=UserRole.CUSTOMER,
            first_name='Alice',
            last_name='Smith',
            password='password123',
        )
        self.customer_a = CustomerProfile.objects.create(
            user=self.user_a,
            customer_code='CUST-ALICE-301',
            address_line='123 Main Street',
            city='Mumbai',
            postal_code='400001',
        )

        # Customer B (Bob - unauthorized intruder)
        self.user_b = User.objects.create_user(
            username='bob_policy',
            email='bob.policy@example.com',
            role=UserRole.CUSTOMER,
            first_name='Bob',
            last_name='Jones',
            password='password123',
        )
        self.customer_b = CustomerProfile.objects.create(
            user=self.user_b,
            customer_code='CUST-BOB-302',
            address_line='789 Outer Circle',
            city='Delhi',
            postal_code='110001',
        )

        # Underwriter Staff
        self.user_uw = User.objects.create_user(
            username='sarah_uw',
            email='sarah.underwriter@example.com',
            role=UserRole.UNDERWRITER,
            first_name='Sarah',
            last_name='Underwriter',
            password='password123',
            is_staff=True,
        )
        self.staff_uw = StaffProfile.objects.create(
            user=self.user_uw,
            staff_code='UW-301',
            department='Underwriting',
        )

        # Administrator
        self.user_admin = User.objects.create_user(
            username='admin_policy',
            email='admin.policy@example.com',
            role=UserRole.ADMINISTRATOR,
            first_name='Super',
            last_name='Admin',
            password='password123',
            is_staff=True,
            is_superuser=True,
        )

        # Vehicle A owned by Customer A
        self.vehicle_a = VehicleService.create_vehicle(
            customer=self.customer_a,
            data={
                'registration_number': 'MH02XY1122',
                'chassis_number': '1HGCR2F83HA112233',
                'make': 'Hyundai',
                'model': 'Creta SX',
                'manufacture_year': 2023,
                'vehicle_type': VehicleType.SUV,
                'fuel_type': FuelType.PETROL,
                'usage_type': UsageType.PERSONAL,
                'vehicle_value': '1500000.00',
            }
        )

        # Vehicle B owned by Customer B
        self.vehicle_b = VehicleService.create_vehicle(
            customer=self.customer_b,
            data={
                'registration_number': 'DL01ZZ9988',
                'chassis_number': '2T3RFREV9KW998877',
                'make': 'Tata',
                'model': 'Nexon EV',
                'manufacture_year': 2024,
                'vehicle_type': VehicleType.SUV,
                'fuel_type': FuelType.ELECTRIC,
                'usage_type': UsageType.PERSONAL,
                'vehicle_value': '1800000.00',
            }
        )

        # Coverage Plan
        self.plan = CoveragePlan.objects.create(
            name='Comprehensive Motor Plan',
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            description='Comprehensive bumper to bumper protection',
            base_rate_percentage=Decimal('2.500'),
            standard_deductible=Decimal('2500.00'),
            includes_own_damage=True,
            includes_third_party=True,
            includes_roadside_assistance=True,
            includes_engine_protection=True,
        )

        # Policy A issued for Customer A
        self.policy_a = Policy.objects.create(
            policy_number='POL-2026-A1A1A1A1',
            customer=self.customer_a,
            vehicle=self.vehicle_a,
            coverage_plan=self.plan,
            underwriter=self.staff_uw,
            premium_amount=Decimal('37500.00'),
            deductible_amount=Decimal('2500.00'),
            duration_years=1,
            start_date=date(2026, 1, 1),
            end_date=date(2027, 1, 1),
            status=PolicyStatus.ACTIVE,
        )

        # Policy B issued for Customer B
        self.policy_b = Policy.objects.create(
            policy_number='POL-2026-B2B2B2B2',
            customer=self.customer_b,
            vehicle=self.vehicle_b,
            coverage_plan=self.plan,
            underwriter=self.staff_uw,
            premium_amount=Decimal('45000.00'),
            deductible_amount=Decimal('2500.00'),
            duration_years=1,
            start_date=date(2026, 2, 1),
            end_date=date(2027, 2, 1),
            status=PolicyStatus.ACTIVE,
        )

    # 1. Policy Detail Access
    def test_policy_detail_access_owner(self, client):
        client.force_login(self.user_a)
        resp = client.get(reverse('policies:detail', kwargs={'pk': self.policy_a.pk}))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'POL-2026-A1A1A1A1' in content
        assert 'MH02XY1122' in content
        assert 'Hyundai' in content
        assert '₹' in content
        assert '37,500.00' in content or '37500' in content

    # 2. Ownership Isolation
    def test_policy_detail_ownership_isolation(self, client):
        # Customer B attempts to view Customer A's policy
        client.force_login(self.user_b)
        resp = client.get(reverse('policies:detail', kwargs={'pk': self.policy_a.pk}))
        assert resp.status_code == 403

    # 3. Certificate Generation
    def test_certificate_generation_by_owner(self, client):
        client.force_login(self.user_a)
        resp = client.get(reverse('policies:certificate', kwargs={'pk': self.policy_a.pk}))
        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/pdf'
        assert f'attachment; filename="Nexisure_Certificate_{self.policy_a.policy_number}.pdf"' in resp['Content-Disposition'] or 'inline;' in resp['Content-Disposition']
        assert resp.content.startswith(b'%PDF')
        assert len(resp.content) > 1000

    # 4. Certificate Authorization
    def test_certificate_authorization_rules(self, client):
        # Customer B cannot download Customer A's certificate
        client.force_login(self.user_b)
        resp = client.get(reverse('policies:certificate', kwargs={'pk': self.policy_a.pk}))
        assert resp.status_code == 403

        # Underwriter can download Customer A's certificate
        client.force_login(self.user_uw)
        resp_uw = client.get(reverse('policies:certificate', kwargs={'pk': self.policy_a.pk}))
        assert resp_uw.status_code == 200
        assert resp_uw['Content-Type'] == 'application/pdf'

        # Administrator can download Customer A's certificate
        client.force_login(self.user_admin)
        resp_admin = client.get(reverse('policies:certificate', kwargs={'pk': self.policy_a.pk}))
        assert resp_admin.status_code == 200
        assert resp_admin['Content-Type'] == 'application/pdf'

    # 5. Endorsement Request
    def test_endorsement_request_creation(self, client):
        client.force_login(self.user_a)
        resp = client.post(
            reverse('policies:endorsement_request', kwargs={'pk': self.policy_a.pk}),
            data={
                'endorsement_type': 'ADDRESS_UPDATE',
                'address': '555 MG Road',
                'city': 'Bengaluru',
                'postal_code': '560001',
                'description': 'Customer relocated to Bengaluru branch office',
            }
        )
        assert resp.status_code == 302

        # Verify ServiceRequest creation
        req = ServiceRequest.objects.filter(policy=self.policy_a).first()
        assert req is not None
        assert req.request_type == ServiceRequestType.ADDRESS_UPDATE
        assert req.status == ServiceRequestStatus.SUBMITTED
        assert req.change_payload.get('city') == 'Bengaluru'
        assert req.change_payload.get('postal_code') == '560001'

    # 6. Endorsement Validation
    def test_endorsement_validation(self, client):
        client.force_login(self.user_b)
        # Customer B cannot request endorsement on Customer A's policy
        resp = client.post(
            reverse('policies:endorsement_request', kwargs={'pk': self.policy_a.pk}),
            data={
                'endorsement_type': 'ADDRESS_UPDATE',
                'address': 'Malicious Address',
                'city': 'Delhi',
                'postal_code': '110001',
            }
        )
        assert resp.status_code == 403

        # Direct service validation check for empty payload
        with pytest.raises(ServiceValidationError):
            PolicyService.request_policy_endorsement(
                policy=self.policy_a,
                customer=self.customer_a,
                endorsement_type='ADDRESS_UPDATE',
                requested_changes={},  # Empty payload
                title='Empty update',
                description='Empty test',
                actor=self.user_a,
            )

    # 7. Endorsement Approval
    def test_endorsement_approval_by_underwriter(self, client):
        # Create request
        srv = PolicyService.request_policy_endorsement(
            policy=self.policy_a,
            customer=self.customer_a,
            endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
            requested_changes={
                'address': '999 Indiranagar 100ft Rd',
                'city': 'Bengaluru',
                'postal_code': '560038',
            },
            title='Address relocation',
            description='Relocating to Bengaluru',
            actor=self.user_a,
        )

        # Underwriter approves
        client.force_login(self.user_uw)
        resp = client.post(
            reverse('policies:endorsement_adjudicate', kwargs={'request_pk': srv.pk}),
            data={'decision': 'APPROVE', 'notes': 'Verified address proof successfully'}
        )
        assert resp.status_code == 302

        # Verify profile updated
        self.customer_a.refresh_from_db()
        assert self.customer_a.address_line == '999 Indiranagar 100ft Rd'
        assert self.customer_a.city == 'Bengaluru'
        assert self.customer_a.postal_code == '560038'

        # Verify ServiceRequest status
        srv.refresh_from_db()
        assert srv.status == ServiceRequestStatus.RESOLVED
        assert srv.assigned_staff == self.user_uw

    # 8. Endorsement Rejection
    def test_endorsement_rejection_by_underwriter(self, client):
        srv = PolicyService.request_policy_endorsement(
            policy=self.policy_a,
            customer=self.customer_a,
            endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
            requested_changes={
                'address': 'Invalid Address',
                'city': 'Nowhere',
                'postal_code': '000000',
            },
            title='Suspicious change',
            description='Customer submitted fake utility bill',
            actor=self.user_a,
        )

        # Underwriter rejects
        client.force_login(self.user_uw)
        resp = client.post(
            reverse('policies:endorsement_adjudicate', kwargs={'request_pk': srv.pk}),
            data={'decision': 'REJECT', 'notes': 'Failed address verification checks'}
        )
        assert resp.status_code == 302

        # Verify profile was NOT updated
        self.customer_a.refresh_from_db()
        assert self.customer_a.address_line == '123 Main Street'
        assert self.customer_a.city == 'Mumbai'

        # Verify ServiceRequest status
        srv.refresh_from_db()
        assert srv.status == ServiceRequestStatus.REJECTED

    # 9. Financial Immutability
    def test_financial_immutability_protection(self):
        # Attempting to mutate premium, deductible, IDV, or policy number must be blocked
        forbidden_payloads = [
            {'premium_amount': '100.00'},
            {'deductible_amount': '0.00'},
            {'policy_number': 'POL-HACKED-001'},
            {'vehicle_value': '5000000.00'},
            {'idv': '5000000.00'},
        ]

        for payload in forbidden_payloads:
            with pytest.raises(ServiceValidationError) as exc:
                PolicyService.request_policy_endorsement(
                    policy=self.policy_a,
                    customer=self.customer_a,
                    endorsement_type=ServiceRequestType.OTHER,
                    requested_changes=payload,
                    title='Malicious Financial Modification',
                    description='Attempting to lower premium',
                    actor=self.user_a,
                )
            assert 'Direct mutation of policy financial or contract identity' in str(exc.value)

    # 10. Cancellation Workflow
    def test_policy_cancellation_workflow(self, client):
        client.force_login(self.user_a)
        resp = client.post(
            reverse('policies:cancel', kwargs={'pk': self.policy_a.pk}),
            data={'reason': 'Vehicle sold to third party'}
        )
        assert resp.status_code == 302

        # Verify policy status is CANCELLED and record is NOT deleted
        self.policy_a.refresh_from_db()
        assert self.policy_a.status == PolicyStatus.CANCELLED
        assert Policy.objects.filter(pk=self.policy_a.pk).exists()

    # 11. Invalid Cancellation Scenarios
    def test_invalid_cancellation_scenarios(self, client):
        # Customer B cannot cancel Customer A's policy
        client.force_login(self.user_b)
        resp = client.post(
            reverse('policies:cancel', kwargs={'pk': self.policy_a.pk}),
            data={'reason': 'Malicious attempt'}
        )
        assert resp.status_code == 403

        # Cancel policy once
        client.force_login(self.user_a)
        client.post(
            reverse('policies:cancel', kwargs={'pk': self.policy_a.pk}),
            data={'reason': 'Valid cancellation'}
        )
        self.policy_a.refresh_from_db()
        assert self.policy_a.status == PolicyStatus.CANCELLED

        # Attempting to cancel already CANCELLED policy raises ServiceValidationError
        with pytest.raises(ServiceValidationError):
            PolicyService.cancel_policy(self.policy_a, actor=self.user_a)

    # 12. Policy Renewal Workflow
    def test_policy_renewal_workflow(self, client):
        client.force_login(self.user_a)
        resp = client.post(
            reverse('policies:renew', kwargs={'pk': self.policy_a.pk}),
            data={'duration_years': '1'}
        )
        assert resp.status_code == 302

        # Retrieve new renewal policy
        new_policy = Policy.objects.filter(previous_policy=self.policy_a).first()
        assert new_policy is not None
        assert new_policy.status == PolicyStatus.ACTIVE
        assert new_policy.policy_number != self.policy_a.policy_number
        assert new_policy.start_date == self.policy_a.end_date + timedelta(days=1)

        # Verify 5% NCB discount on renewal
        expected_base = (self.policy_a.vehicle.vehicle_value * self.plan.base_rate_percentage) / Decimal('100.00')
        expected_ncb_premium = round(expected_base * Decimal('0.95'), 2)
        assert new_policy.premium_amount == expected_ncb_premium

        # Verify old policy transitioned to RENEWED
        self.policy_a.refresh_from_db()
        assert self.policy_a.status == PolicyStatus.RENEWED

    # 13. Renewal Lineage Preservation
    def test_renewal_lineage_preservation(self):
        new_policy = PolicyService.renew_policy(
            existing_policy=self.policy_a,
            duration_years=1,
        )

        assert new_policy.previous_policy == self.policy_a
        assert self.policy_a.renewal_history.first() == new_policy

        lineage = get_policy_renewal_lineage(new_policy)
        assert len(lineage) == 2
        assert lineage[0] == self.policy_a
        assert lineage[1] == new_policy

    # 14. Duplicate Renewal Prevention
    def test_duplicate_renewal_prevention(self):
        PolicyService.renew_policy(
            existing_policy=self.policy_a,
            duration_years=1,
        )

        # Attempting to renew the already RENEWED policy raises ServiceValidationError
        self.policy_a.refresh_from_db()
        with pytest.raises(ServiceValidationError) as exc:
            PolicyService.renew_policy(existing_policy=self.policy_a, duration_years=1)
        assert "Cannot renew policy with status 'RENEWED'" in str(exc.value) or "already been renewed" in str(exc.value)

    # 15. Audit Events
    def test_audit_events_emitted(self):
        # 1. Certificate generation audit
        PolicyService.generate_policy_certificate(self.policy_a, actor=self.user_a)
        cert_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_CERTIFICATE_GENERATED,
            target_id=str(self.policy_a.pk)
        ).first()
        assert cert_audit is not None

        # 2. Endorsement requested audit
        srv = PolicyService.request_policy_endorsement(
            policy=self.policy_a,
            customer=self.customer_a,
            endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
            requested_changes={'city': 'Pune'},
            title='Pune Address',
            description='City relocation',
            actor=self.user_a,
        )
        req_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_ENDORSEMENT_REQUESTED,
            target_id=str(self.policy_a.pk)
        ).first()
        assert req_audit is not None

        # 3. Endorsement approved audit
        PolicyService.adjudicate_endorsement(
            service_request=srv,
            reviewer=self.user_uw,
            decision='APPROVE',
            notes='Address confirmed',
        )
        app_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_ENDORSEMENT_APPROVED,
            target_id=str(self.policy_a.pk)
        ).first()
        assert app_audit is not None

        # 4. Endorsement rejected audit
        srv2 = PolicyService.request_policy_endorsement(
            policy=self.policy_a,
            customer=self.customer_a,
            endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
            requested_changes={'city': 'FakeCity'},
            title='Fake Address',
            description='Invalid',
            actor=self.user_a,
        )
        PolicyService.adjudicate_endorsement(
            service_request=srv2,
            reviewer=self.user_uw,
            decision='REJECT',
            notes='Invalid location',
        )
        rej_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_ENDORSEMENT_REJECTED,
            target_id=str(self.policy_a.pk)
        ).first()
        assert rej_audit is not None

        # 5. Policy cancelled audit
        PolicyService.cancel_policy(self.policy_a, actor=self.user_a, reason='Sold car')
        cancel_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_CANCELLED,
            target_id=str(self.policy_a.pk)
        ).first()
        assert cancel_audit is not None

        # 6. Policy renewed audit (on Policy B)
        renewed_b = PolicyService.renew_policy(self.policy_b)
        renew_audit = AuditLog.objects.filter(
            action=AuditAction.POLICY_RENEWED,
            target_id=str(renewed_b.pk)
        ).first()
        assert renew_audit is not None

    # 16. RBAC & Self-Approval Prevention
    def test_rbac_and_self_approval_protection(self, client):
        # Create endorsement request for Customer A
        srv = PolicyService.request_policy_endorsement(
            policy=self.policy_a,
            customer=self.customer_a,
            endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
            requested_changes={'city': 'Chennai'},
            title='Self-approval check',
            description='Testing customer approval',
            actor=self.user_a,
        )

        # Customer A attempts to approve their own endorsement via POST -> 403
        client.force_login(self.user_a)
        resp = client.post(
            reverse('policies:endorsement_adjudicate', kwargs={'request_pk': srv.pk}),
            data={'decision': 'APPROVE', 'notes': 'I approve my own request'}
        )
        assert resp.status_code == 403

        # Unauthenticated user redirected to login
        client.logout()
        resp_unauth = client.get(reverse('policies:detail', kwargs={'pk': self.policy_a.pk}))
        assert resp_unauth.status_code == 302
        assert '/login/' in resp_unauth['Location']

    # 17. CSRF / State-Changing Endpoints
    def test_csrf_protection_on_state_modifying_endpoints(self):
        from django.test import Client
        enforcing_client = Client(enforce_csrf_checks=True)
        enforcing_client.force_login(self.user_a)

        # POST without CSRF token must be rejected with HTTP 403
        resp_renew = enforcing_client.post(reverse('policies:renew', kwargs={'pk': self.policy_a.pk}), data={'duration_years': '1'})
        assert resp_renew.status_code == 403

        resp_cancel = enforcing_client.post(reverse('policies:cancel', kwargs={'pk': self.policy_a.pk}), data={'reason': 'No token'})
        assert resp_cancel.status_code == 403

        resp_endorse = enforcing_client.post(reverse('policies:endorsement_request', kwargs={'pk': self.policy_a.pk}), data={'endorsement_type': 'ADDRESS_UPDATE'})
        assert resp_endorse.status_code == 403

    # 18. INR Currency Presentation
    def test_inr_currency_presentation_in_ui(self, client):
        client.force_login(self.user_a)
        resp = client.get(reverse('policies:detail', kwargs={'pk': self.policy_a.pk}))
        assert resp.status_code == 200
        html = resp.content.decode('utf-8')

        # Assert INR symbol presence
        assert '₹' in html
        assert '₹37,500.00' in html or '₹37500' in html
        assert '₹2,500.00' in html or '₹2500' in html
        assert '₹1,500,000.00' in html or '₹1500000' in html

        # Ensure no dollar symbols in monetary fields
        assert '$' not in html
