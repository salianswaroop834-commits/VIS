import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.test import Client
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffProfile
from staff.services.staff_service import StaffService
from vehicles.models import Vehicle, VehicleType
from vehicles.services.vehicle_service import VehicleService
from quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from quotations.services.quotation_service import QuotationService
from policies.models import Policy, PolicyStatus
from policies.services.policy_service import PolicyService
from claims.models import Claim, ClaimStatus
from claims.services.claim_service import ClaimService
from service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from service_requests.services.service_request_service import ServiceRequestService
from audit.models import AuditLog, AuditAction
from audit.services.audit_service import AuditService
from core.services import ServiceValidationError


@pytest.fixture
def audit_test_data(db):
    # Admin User
    admin_user = User.objects.create_user(
        username='admin_boss',
        email='admin@nexisure.internal',
        role=UserRole.ADMINISTRATOR,
        password='password123',
    )

    # Underwriter 1 (Outgoing)
    uw1_user = User.objects.create_user(
        username='uw_alice',
        email='alice.uw@nexisure.internal',
        role=UserRole.UNDERWRITER,
        password='password123',
    )
    uw1_staff = StaffProfile.objects.create(
        user=uw1_user,
        staff_code='UW-001',
        department='Underwriting',
    )

    # Underwriter 2 (Successor)
    uw2_user = User.objects.create_user(
        username='uw_bob',
        email='bob.uw@nexisure.internal',
        role=UserRole.UNDERWRITER,
        password='password123',
    )
    uw2_staff = StaffProfile.objects.create(
        user=uw2_user,
        staff_code='UW-002',
        department='Underwriting',
    )

    # Claims Handler 1 (Outgoing)
    ch1_user = User.objects.create_user(
        username='ch_carol',
        email='carol.ch@nexisure.internal',
        role=UserRole.CLAIMS_HANDLER,
        password='password123',
    )
    ch1_staff = StaffProfile.objects.create(
        user=ch1_user,
        staff_code='CH-001',
        department='Claims',
        max_claim_approval_limit=Decimal('15000.00'),
    )

    # Claims Handler 2 (Successor)
    ch2_user = User.objects.create_user(
        username='ch_david',
        email='david.ch@nexisure.internal',
        role=UserRole.CLAIMS_HANDLER,
        password='password123',
    )
    ch2_staff = StaffProfile.objects.create(
        user=ch2_user,
        staff_code='CH-002',
        department='Claims',
        max_claim_approval_limit=Decimal('20000.00'),
    )

    # Customer
    cust_user = User.objects.create_user(
        username='cust_emma',
        email='emma@example.com',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    customer = CustomerProfile.objects.create(
        user=cust_user,
        customer_code='CUST-EMMA-01',
        city='Seattle',
        state='WA',
        postal_code='98101',
    )

    # Vehicle
    vehicle = Vehicle.objects.create(
        customer=customer,
        registration_number='WA99ZZ9999',
        vehicle_type=VehicleType.SEDAN,
        make='Tesla',
        model='Model 3',
        manufacture_year=2023,
        chassis_number='5YJ3E1EB8NF999999',
        vehicle_value=Decimal('42000.00'),
    )

    # Plan
    plan, _ = CoveragePlan.objects.get_or_create(
        plan_code=CoveragePlanCode.COMPREHENSIVE,
        defaults={
            'name': 'Comprehensive Vehicle Shield',
            'base_rate_percentage': Decimal('2.850'),
            'description': 'Full vehicle protection',
        }
    )

    # Active Policy assigned to Underwriter 1
    # Start 30 days before today to avoid UTC/IST boundary issues when filing claims with timezone.now()
    today = date.today()
    policy_start = today - timedelta(days=30)
    policy = Policy.objects.create(
        policy_number='POL-2026-AUDIT01',
        customer=customer,
        vehicle=vehicle,
        coverage_plan=plan,
        underwriter=uw1_staff,
        start_date=policy_start,
        end_date=policy_start.replace(year=policy_start.year + 1),
        premium_amount=Decimal('1197.00'),
        deductible_amount=Decimal('1000.00'),
        status=PolicyStatus.ACTIVE,
    )

    return {
        'admin_user': admin_user,
        'uw1_staff': uw1_staff,
        'uw2_staff': uw2_staff,
        'ch1_staff': ch1_staff,
        'ch2_staff': ch2_staff,
        'customer': customer,
        'vehicle': vehicle,
        'policy': policy,
    }


@pytest.mark.django_db
class TestAuditLoggingAndGovernance:

    def test_audit_service_log_creation(self, audit_test_data):
        entry = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
            details={'note': 'Manual compliance check passed'},
            ip_address='192.168.1.10',
        )

        assert entry.pk is not None
        assert entry.action == AuditAction.POLICY_CREATED
        assert entry.actor_email == 'admin@nexisure.internal'
        assert entry.actor_role == UserRole.ADMINISTRATOR
        assert entry.ip_address == '192.168.1.10'
        assert entry.is_success is True

    def test_underwriter_workload_reassignment(self, audit_test_data):
        uw1 = audit_test_data['uw1_staff']
        uw2 = audit_test_data['uw2_staff']
        policy = audit_test_data['policy']

        assert policy.underwriter == uw1

        # Reassign from UW1 to UW2
        reassigned_count = StaffService.reassign_underwriter_workload(
            from_staff=uw1,
            to_staff=uw2,
            actor=audit_test_data['admin_user'],
        )

        assert reassigned_count == 1
        policy.refresh_from_db()
        assert policy.underwriter == uw2

        # Verify Audit Logs
        policy_log = AuditLog.objects.filter(
            action=AuditAction.POLICY_REASSIGNED,
            target_id=str(policy.pk),
        ).first()
        assert policy_log is not None
        assert policy_log.details['from_underwriter'] == 'UW-001'
        assert policy_log.details['to_underwriter'] == 'UW-002'

        staff_log = AuditLog.objects.filter(
            action=AuditAction.STAFF_REASSIGNED,
            target_id=str(uw1.pk),
        ).first()
        assert staff_log is not None
        assert staff_log.details['policies_reassigned'] == 1

    def test_underwriter_deactivation_blocked_when_active_policies_exist(self, audit_test_data):
        uw1 = audit_test_data['uw1_staff']

        # UW1 still has active policy POL-2026-AUDIT01
        with pytest.raises(ServiceValidationError, match="active policy/policies currently assigned"):
            StaffService.deactivate_staff(uw1, actor=audit_test_data['admin_user'])

        # UW1 remains active
        uw1.refresh_from_db()
        assert uw1.is_active is True
        assert uw1.user.is_active is True

    def test_underwriter_deactivation_succeeds_after_reassignment(self, audit_test_data):
        uw1 = audit_test_data['uw1_staff']
        uw2 = audit_test_data['uw2_staff']

        # Reassign workload first
        StaffService.reassign_underwriter_workload(uw1, uw2, actor=audit_test_data['admin_user'])

        # Now deactivation succeeds
        deactivated = StaffService.deactivate_staff(uw1, actor=audit_test_data['admin_user'])
        assert deactivated.is_active is False
        assert deactivated.user.is_active is False

        # Verify deactivation audit log
        log = AuditLog.objects.filter(
            action=AuditAction.STAFF_DELETED,
            target_id=str(uw1.pk),
        ).first()
        assert log is not None
        assert log.details['deactivated'] is True

    def test_claims_handler_workload_reassignment(self, audit_test_data):
        ch1 = audit_test_data['ch1_staff']
        ch2 = audit_test_data['ch2_staff']

        # Customer files claim
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Highway 520',
            incident_description='Minor sideswipe during merge',
            estimated_loss_amount=Decimal('1800.00'),
        )

        # CH1 self-assigns claim
        ClaimService.self_assign_claim(claim, ch1)
        claim.refresh_from_db()
        assert claim.handler == ch1
        assert claim.status == ClaimStatus.IN_REVIEW

        # Reassign to CH2
        count = StaffService.reassign_handler_workload(
            from_staff=ch1,
            to_staff=ch2,
            actor=audit_test_data['admin_user'],
        )
        assert count == 1
        claim.refresh_from_db()
        assert claim.handler == ch2
        assert claim.status == ClaimStatus.IN_REVIEW

        # Verify audit logs
        log = AuditLog.objects.filter(
            action=AuditAction.CLAIM_ASSIGNED,
            target_id=str(claim.pk),
        ).order_by('-created_at').first()
        assert log is not None
        assert log.details['from_handler'] == 'CH-001'
        assert log.details['to_handler'] == 'CH-002'

    def test_claims_handler_workload_return_to_queue(self, audit_test_data):
        ch1 = audit_test_data['ch1_staff']

        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Downtown Garage',
            incident_description='Pillar scrape on rear bumper',
            estimated_loss_amount=Decimal('900.00'),
        )
        ClaimService.self_assign_claim(claim, ch1)

        # Return claims to shared queue
        count = StaffService.reassign_handler_workload(
            from_staff=ch1,
            return_to_queue=True,
            actor=audit_test_data['admin_user'],
        )
        assert count == 1
        claim.refresh_from_db()
        assert claim.handler is None
        assert claim.status == ClaimStatus.PENDING

    def test_claims_handler_deactivation_blocked_with_in_review_claims(self, audit_test_data):
        ch1 = audit_test_data['ch1_staff']

        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Broadway & Pine',
            incident_description='Rear mirror cracked',
            estimated_loss_amount=Decimal('400.00'),
        )
        ClaimService.self_assign_claim(claim, ch1)

        # Deactivation should fail
        with pytest.raises(ServiceValidationError, match="currently in review"):
            StaffService.deactivate_staff(ch1, actor=audit_test_data['admin_user'])

        ch1.refresh_from_db()
        assert ch1.is_active is True

    def test_important_business_actions_generate_audit_records(self, audit_test_data):
        customer = audit_test_data['customer']
        policy = audit_test_data['policy']

        # 1. Claim filing generates CLAIM_CREATED
        claim = ClaimService.file_claim(
            customer=customer,
            policy=policy,
            incident_date=timezone.now(),
            incident_location='1st Ave',
            incident_description='Minor collision',
            estimated_loss_amount=Decimal('800.00'),
        )
        assert AuditLog.objects.filter(action=AuditAction.CLAIM_CREATED, target_id=str(claim.pk)).exists()

        # 2. Service request creation generates SERVICE_REQUEST_CREATED
        srv = ServiceRequestService.create_service_request(
            customer=customer,
            request_type=ServiceRequestType.POLICY_SERVICE,
            title='Inquiry on Coverage',
            description='Customer asks about towing',
            policy=policy,
        )
        assert AuditLog.objects.filter(action=AuditAction.SERVICE_REQUEST_CREATED, target_id=str(srv.pk)).exists()

        # 3. Handler self-assignment generates CLAIM_ASSIGNED
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])
        assert AuditLog.objects.filter(action=AuditAction.CLAIM_ASSIGNED, target_id=str(claim.pk)).exists()

        # 4. Handler claim approval generates CLAIM_APPROVED
        ClaimService.approve_claim(claim, handler=audit_test_data['ch1_staff'], settlement_amount=Decimal('700.00'))
        assert AuditLog.objects.filter(action=AuditAction.CLAIM_APPROVED, target_id=str(claim.pk)).exists()

    def test_audit_actor_and_target_integrity(self, audit_test_data):
        customer = audit_test_data['customer']
        policy = audit_test_data['policy']

        claim = ClaimService.file_claim(
            customer=customer,
            policy=policy,
            incident_date=timezone.now(),
            incident_location='Belltown',
            incident_description='Front dent',
            estimated_loss_amount=Decimal('600.00'),
        )
        log = AuditLog.objects.filter(action=AuditAction.CLAIM_CREATED, target_id=str(claim.pk)).first()
        assert log is not None
        assert log.actor == customer.user
        assert log.actor_email == customer.user.email
        assert log.actor_role == UserRole.CUSTOMER
        assert log.target_entity == 'Claim'
        assert log.target_id == str(claim.pk)

    def test_audit_metadata_is_structured(self, audit_test_data):
        customer = audit_test_data['customer']
        policy = audit_test_data['policy']

        claim = ClaimService.file_claim(
            customer=customer,
            policy=policy,
            incident_date=timezone.now(),
            incident_location='Capitol Hill',
            incident_description='Side mirror broken',
            estimated_loss_amount=Decimal('350.00'),
        )
        log = AuditLog.objects.filter(action=AuditAction.CLAIM_CREATED, target_id=str(claim.pk)).first()
        assert isinstance(log.details, dict)
        assert 'claim_number' in log.details
        assert 'policy_number' in log.details
        assert 'estimated_loss' in log.details
        assert log.details['estimated_loss'] == 350.00

    def test_audit_sensitive_values_are_redacted(self, audit_test_data):
        log = AuditService.log(
            action=AuditAction.USER_LOGIN,
            target_entity='User',
            target_id=str(audit_test_data['admin_user'].pk),
            actor=audit_test_data['admin_user'],
            details={
                'password': 'SuperSecretPassword!123',
                'access_token': 'eyJh...very_sensitive_token',
                'cvv': '789',
                'card_number': '4111222233334444',
                'normal_key': 'safe_value',
            }
        )
        assert log.details['password'] == '[REDACTED]'
        assert log.details['access_token'] == '[REDACTED]'
        assert log.details['cvv'] == '[REDACTED]'
        assert log.details['card_number'] == '[REDACTED]'
        assert log.details['normal_key'] == 'safe_value'

    def test_audit_log_instance_cannot_be_modified(self, audit_test_data):
        log = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
        )
        log.action = AuditAction.POLICY_CANCELLED
        with pytest.raises(PermissionDenied, match="Audit log entries are immutable"):
            log.save()

    def test_audit_log_queryset_cannot_be_bulk_updated(self, audit_test_data):
        log = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
        )
        with pytest.raises(PermissionDenied, match="Bulk updates are strictly prohibited"):
            AuditLog.objects.filter(pk=log.pk).update(action=AuditAction.POLICY_CANCELLED)

    def test_audit_log_instance_cannot_be_deleted(self, audit_test_data):
        log = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
        )
        with pytest.raises(PermissionDenied, match="permanent compliance records and cannot be deleted"):
            log.delete()

    def test_audit_log_queryset_cannot_be_bulk_deleted(self, audit_test_data):
        log = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
        )
        with pytest.raises(PermissionDenied, match="Bulk deletion is strictly prohibited"):
            AuditLog.objects.filter(pk=log.pk).delete()

    def test_rbac_unauthorized_users_blocked_from_audit_explorer(self, audit_test_data):
        client = Client()

        # Customer is forbidden (403)
        client.force_login(audit_test_data['customer'].user)
        res = client.get(reverse('audit:list'))
        assert res.status_code == 403

        # Underwriter is forbidden (403)
        client.force_login(audit_test_data['uw1_staff'].user)
        res = client.get(reverse('audit:list'))
        assert res.status_code == 403

        # Claims Handler is forbidden (403)
        client.force_login(audit_test_data['ch1_staff'].user)
        res = client.get(reverse('audit:list'))
        assert res.status_code == 403

    def test_rbac_administrator_can_explore_and_filter_audit_logs(self, audit_test_data):
        client = Client()
        client.force_login(audit_test_data['admin_user'])

        # Create sample log
        log = AuditService.log(
            action=AuditAction.POLICY_CREATED,
            target_entity='Policy',
            target_id=str(audit_test_data['policy'].pk),
            actor=audit_test_data['admin_user'],
        )

        # 1. Main list view
        res = client.get(reverse('audit:list'))
        assert res.status_code == 200
        assert 'action_choices' in res.context

        # 2. Filter by action
        res = client.get(f"{reverse('audit:list')}?action={AuditAction.POLICY_CREATED}")
        assert res.status_code == 200

        # 3. Filter by actor
        res = client.get(f"{reverse('audit:list')}?actor=admin_boss")
        assert res.status_code == 200

        # 4. Filter by target entity
        res = client.get(f"{reverse('audit:list')}?target_entity=Policy")
        assert res.status_code == 200

        # 5. Detail view
        res = client.get(reverse('audit:detail', kwargs={'pk': log.pk}))
        assert res.status_code == 200
        assert res.context['log'].pk == log.pk

    def test_audit_explorer_shows_empty_state_without_hardcoded_rows(self, audit_test_data):
        client = Client()
        client.force_login(audit_test_data['admin_user'])

        res = client.get(f"{reverse('audit:list')}?actor=nonexistent_phantom_actor_12345@domain.com")
        assert res.status_code == 200
        assert b"No Audit Records Found" in res.content

    def test_issued_policy_financial_fields_remain_immutable(self, audit_test_data):
        policy = audit_test_data['policy']

        policy.premium_amount = Decimal('10.00')
        with pytest.raises(ServiceValidationError, match="Cannot modify immutable financial field 'premium_amount'"):
            policy.save()

        policy.refresh_from_db()
        policy.deductible_amount = Decimal('0.00')
        with pytest.raises(ServiceValidationError, match="Cannot modify immutable financial field 'deductible_amount'"):
            policy.save()

        policy.refresh_from_db()
        policy.policy_number = 'POL-TAMPERED-999'
        with pytest.raises(ServiceValidationError, match="Cannot modify policy contract identifier 'policy_number'"):
            policy.save()

    def test_invalid_policy_renewal_is_blocked(self, audit_test_data):
        policy = audit_test_data['policy']

        # First renewal succeeds
        renewed = PolicyService.renew_policy(policy, duration_years=1)
        assert renewed.status == PolicyStatus.ACTIVE
        policy.refresh_from_db()
        assert policy.status == PolicyStatus.RENEWED

        # Attempting to renew the already-renewed policy is blocked by status check
        with pytest.raises(ServiceValidationError, match="Cannot renew policy with status 'RENEWED'"):
            PolicyService.renew_policy(policy, duration_years=1)

        # Also test renewal history duplicate guard when policy is still marked active
        Policy.objects.filter(pk=policy.pk).update(status=PolicyStatus.ACTIVE)
        policy.refresh_from_db()
        with pytest.raises(ServiceValidationError, match="already been renewed"):
            PolicyService.renew_policy(policy, duration_years=1)

    def test_invalid_policy_cancellation_is_blocked(self, audit_test_data):
        policy = audit_test_data['policy']

        # Cancel policy
        PolicyService.cancel_policy(policy, actor=audit_test_data['admin_user'])
        policy.refresh_from_db()
        assert policy.status == PolicyStatus.CANCELLED

        # Attempting to cancel already-cancelled policy fails
        with pytest.raises(ServiceValidationError, match="Only ACTIVE policies may be cancelled"):
            PolicyService.cancel_policy(policy, actor=audit_test_data['admin_user'])

    def test_policy_endorsement_cannot_mutate_immutable_financial_fields(self, audit_test_data):
        policy = audit_test_data['policy']

        with pytest.raises(ServiceValidationError, match="Direct mutation of policy financial or contract identity field"):
            PolicyService.request_policy_endorsement(
                policy=policy,
                customer=audit_test_data['customer'],
                endorsement_type=ServiceRequestType.ADDRESS_UPDATE,
                requested_changes={'premium_amount': 250.00, 'city': 'Portland'},
                title='Unauthorized Premium Modification',
                description='Customer attempting to lower premium',
                actor=audit_test_data['customer'].user,
            )

    def test_claim_settlement_requires_prior_approval(self, audit_test_data):
        # 1. Pending claim cannot be settled
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Denny Way',
            incident_description='Parked scrape',
            estimated_loss_amount=Decimal('450.00'),
        )
        with pytest.raises(ServiceValidationError, match="Only APPROVED claims can be settled"):
            ClaimService.settle_claim(claim, actor=audit_test_data['ch1_staff'])

        # 2. Rejected claim cannot be settled
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])
        ClaimService.reject_claim(claim, handler=audit_test_data['ch1_staff'], rejection_reason="Pre-existing wear and tear")
        claim.refresh_from_db()
        assert claim.status == ClaimStatus.REJECTED

        with pytest.raises(ServiceValidationError, match="Only APPROVED claims can be settled"):
            ClaimService.settle_claim(claim, actor=audit_test_data['ch1_staff'])

    def test_approved_claim_settlement_and_duplicate_prevention(self, audit_test_data):
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Alki Beach',
            incident_description='Fender bender',
            estimated_loss_amount=Decimal('1200.00'),
        )
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])
        ClaimService.approve_claim(claim, handler=audit_test_data['ch1_staff'], settlement_amount=Decimal('1100.00'))
        claim.refresh_from_db()
        assert claim.status == ClaimStatus.APPROVED

        # Settle once
        settled_claim = ClaimService.settle_claim(claim, actor=audit_test_data['ch1_staff'])
        assert settled_claim.status == ClaimStatus.SETTLED
        assert settled_claim.settlement_reference.startswith("SIM-SETTLE-")
        assert settled_claim.settled_at is not None

        # Verify audit log
        assert AuditLog.objects.filter(action=AuditAction.CLAIM_SETTLED, target_id=str(settled_claim.pk)).exists()

        # Settle again is blocked
        with pytest.raises(ServiceValidationError, match="Claim has already been settled"):
            ClaimService.settle_claim(settled_claim, actor=audit_test_data['ch1_staff'])

    def test_claim_settlement_cannot_exceed_approved_amount(self, audit_test_data):
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Mercer St',
            incident_description='Rear bumper hit',
            estimated_loss_amount=Decimal('800.00'),
        )
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])
        ClaimService.approve_claim(claim, handler=audit_test_data['ch1_staff'], settlement_amount=Decimal('750.00'))

        with pytest.raises(ServiceValidationError, match="cannot exceed authorized approval amount"):
            ClaimService.settle_claim(claim, actor=audit_test_data['ch1_staff'], settlement_amount=Decimal('900.00'))

    def test_claim_handler_authorization_enforced(self, audit_test_data):
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Westlake Ave',
            incident_description='Bicycle scrape',
            estimated_loss_amount=Decimal('300.00'),
        )
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])

        # CH2 cannot approve CH1's claim
        with pytest.raises(ServiceValidationError, match="You may only action claims assigned to you"):
            ClaimService.approve_claim(claim, handler=audit_test_data['ch2_staff'], settlement_amount=Decimal('300.00'))

        # CH2 cannot reject CH1's claim
        with pytest.raises(ServiceValidationError, match="You may only action claims assigned to you"):
            ClaimService.reject_claim(claim, handler=audit_test_data['ch2_staff'], rejection_reason="Unauthorized rejection")

    def test_finalized_claims_cannot_be_arbitrarily_reopened(self, audit_test_data):
        # 1. Rejected claim cannot be reopened to IN_REVIEW or PENDING
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Eastlake',
            incident_description='Front bumper scratch',
            estimated_loss_amount=Decimal('250.00'),
        )
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])
        ClaimService.reject_claim(claim, handler=audit_test_data['ch1_staff'], rejection_reason="Driver not covered")
        claim.refresh_from_db()
        assert claim.status == ClaimStatus.REJECTED

        claim.status = ClaimStatus.IN_REVIEW
        with pytest.raises(ServiceValidationError, match="Finalized claims cannot be reopened"):
            claim.save()

        claim.refresh_from_db()
        claim.status = ClaimStatus.PENDING
        with pytest.raises(ServiceValidationError, match="Finalized claims cannot be reopened"):
            claim.save()

        # 2. Approved claim cannot be reopened to PENDING
        claim2 = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='South Lake Union',
            incident_description='Mirror broke',
            estimated_loss_amount=Decimal('300.00'),
        )
        ClaimService.self_assign_claim(claim2, audit_test_data['ch1_staff'])
        ClaimService.approve_claim(claim2, handler=audit_test_data['ch1_staff'], settlement_amount=Decimal('300.00'))
        claim2.refresh_from_db()

        claim2.status = ClaimStatus.PENDING
        with pytest.raises(ServiceValidationError, match="Approved claims can only proceed to SETTLED"):
            claim2.save()

    def test_service_request_invalid_state_transitions_blocked(self, audit_test_data):
        srv = ServiceRequestService.create_service_request(
            customer=audit_test_data['customer'],
            request_type=ServiceRequestType.POLICY_SERVICE,
            title='Coverage query',
            description='Customer wants details',
            policy=audit_test_data['policy'],
        )
        assert srv.status == ServiceRequestStatus.SUBMITTED

        with pytest.raises(ServiceValidationError, match="Invalid status"):
            ServiceRequestService.update_status(srv, staff_user=audit_test_data['uw1_staff'].user, new_status='NONEXISTENT')

    def test_terminal_service_request_cannot_be_modified(self, audit_test_data):
        srv = ServiceRequestService.create_service_request(
            customer=audit_test_data['customer'],
            request_type=ServiceRequestType.POLICY_SERVICE,
            title='Address check',
            description='Verify address',
            policy=audit_test_data['policy'],
        )
        ServiceRequestService.update_status(
            srv,
            staff_user=audit_test_data['uw1_staff'].user,
            new_status=ServiceRequestStatus.RESOLVED,
            resolution_notes='Completed',
        )
        srv.refresh_from_db()
        assert srv.status == ServiceRequestStatus.RESOLVED

        with pytest.raises(ServiceValidationError, match="Cannot update service request in terminal state"):
            ServiceRequestService.update_status(
                srv,
                staff_user=audit_test_data['uw1_staff'].user,
                new_status=ServiceRequestStatus.IN_PROGRESS,
            )

    def test_service_request_cross_customer_resource_access_blocked(self, audit_test_data):
        other_user = User.objects.create_user(
            username='hacker_bob',
            email='bob.hacker@example.com',
            role=UserRole.CUSTOMER,
            password='password123',
        )
        other_customer = CustomerProfile.objects.create(
            user=other_user,
            customer_code='CUST-HACK-01',
        )

        with pytest.raises(ServiceValidationError, match="You may only file service requests against your own policies"):
            ServiceRequestService.create_service_request(
                customer=other_customer,
                request_type=ServiceRequestType.POLICY_SERVICE,
                title='Illegitimate Request',
                description='Trying to access Emma policy',
                policy=audit_test_data['policy'],
            )

    def test_vehicle_active_policy_mutation_restrictions(self, audit_test_data):
        vehicle = audit_test_data['vehicle']
        customer = audit_test_data['customer']

        # Attempt to change valuation of vehicle covered by active policy
        with pytest.raises(ServiceValidationError, match="Vehicle valuation .* is locked by an active policy"):
            VehicleService.update_vehicle(
                vehicle=vehicle,
                customer=customer,
                data={'vehicle_value': Decimal('99000.00')},
            )

        # Attempt to deactivate vehicle covered by active policy
        with pytest.raises(ServiceValidationError, match="covered under an active insurance policy"):
            VehicleService.deactivate_vehicle(
                vehicle=vehicle,
                customer=customer,
            )

    def test_quotation_integrity_preserved_on_save(self, audit_test_data):
        draft = QuotationService.create_quotation_draft(
            customer=audit_test_data['customer'],
            vehicle=audit_test_data['vehicle'],
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            vehicle_value=audit_test_data['vehicle'].vehicle_value,
            duration_years=1,
        )
        QuotationService.accept_quotation(draft, actor=audit_test_data['customer'].user)
        draft.refresh_from_db()
        assert draft.status == QuotationDraft.QuotationStatus.ACCEPTED

        draft.calculated_premium = Decimal('10.00')
        with pytest.raises(ServiceValidationError, match="Cannot modify financial fields of quotation"):
            draft.save()

    def test_claim_note_added_generates_audit_event(self, audit_test_data):
        claim = ClaimService.file_claim(
            customer=audit_test_data['customer'],
            policy=audit_test_data['policy'],
            incident_date=timezone.now(),
            incident_location='Aurora Ave',
            incident_description='Rear lamp shattered',
            estimated_loss_amount=Decimal('280.00'),
        )
        ClaimService.self_assign_claim(claim, audit_test_data['ch1_staff'])

        ClaimService.add_claim_note(
            claim,
            actor=audit_test_data['ch1_staff'],
            note="Inspected lamp photos; damage consistent with reported accident."
        )

        assert AuditLog.objects.filter(
            action=AuditAction.CLAIM_NOTE_ADDED,
            target_id=str(claim.pk),
        ).exists()

    def test_security_unauthenticated_requests_redirect_to_login(self, audit_test_data):
        client = Client()
        res = client.get(reverse('audit:list'))
        assert res.status_code == 302
        assert '/auth/login/' in res.headers['Location']

    def test_security_csrf_enforced_on_state_changing_views(self, audit_test_data):
        client = Client(enforce_csrf_checks=True)
        # Attempt POST without CSRF token
        res = client.post(reverse('accounts:logout'))
        assert res.status_code == 403

