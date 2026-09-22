import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile
from apps.vehicles.models import Vehicle, VehicleType
from apps.quotations.models import CoveragePlan, CoveragePlanCode
from apps.policies.models import Policy, PolicyStatus
from apps.claims.models import Claim, ClaimStatus, ClaimDocument, ClaimEvent, ClaimEventType
from apps.claims.services.claim_service import ClaimService
from apps.service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from apps.service_requests.services.service_request_service import ServiceRequestService
from apps.audit.models import AuditLog, AuditAction
from core.services import ServiceValidationError


@pytest.fixture
def phase4_data(db):
    """
    Comprehensive test fixture providing:
    - Customer A & Customer B (with profile, vehicle, and active policies)
    - Claims Handler Dan (and second handler Dave)
    - Underwriter Sue
    - Administrator Adam
    - Expired policy for boundary validation
    """
    # Customer A (Alice)
    cust_a_user = User.objects.create_user(
        username='alice_cust_p4',
        email='alice.p4@example.com',
        phone_number='+919876543210',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    cust_a = CustomerProfile.objects.create(
        user=cust_a_user,
        customer_code='CUST-CLM-001',
        city='Mumbai',
        state='Maharashtra',
        postal_code='400001',
    )

    # Customer B (Bob - unauthorized cross-customer)
    cust_b_user = User.objects.create_user(
        username='bob_cust_p4',
        email='bob.p4@example.com',
        phone_number='+919876543211',
        role=UserRole.CUSTOMER,
        password='password123',
    )
    cust_b = CustomerProfile.objects.create(
        user=cust_b_user,
        customer_code='CUST-CLM-002',
        city='Pune',
        state='Maharashtra',
        postal_code='411001',
    )

    # Claims Handler 1 (Dan)
    handler_user = User.objects.create_user(
        username='dan_handler_p4',
        email='dan.handler@nexisure.internal',
        role=UserRole.CLAIMS_HANDLER,
        password='password123',
    )
    handler_staff = StaffProfile.objects.create(
        user=handler_user,
        staff_code='EMP-CLM-01',
        department='Claims',
        max_claim_approval_limit=Decimal('50000.00'),
    )

    # Claims Handler 2 (Dave - another handler)
    other_handler_user = User.objects.create_user(
        username='dave_handler_p4',
        email='dave.handler@nexisure.internal',
        role=UserRole.CLAIMS_HANDLER,
        password='password123',
    )
    other_handler_staff = StaffProfile.objects.create(
        user=other_handler_user,
        staff_code='EMP-CLM-02',
        department='Claims',
        max_claim_approval_limit=Decimal('40000.00'),
    )

    # Underwriter (Sue)
    uw_user = User.objects.create_user(
        username='sue_uw_p4',
        email='sue.uw@nexisure.internal',
        role=UserRole.UNDERWRITER,
        password='password123',
    )
    uw_staff = StaffProfile.objects.create(
        user=uw_user,
        staff_code='EMP-UW-01',
        department='Underwriting',
        max_claim_approval_limit=Decimal('100000.00'),
    )

    # Administrator (Adam)
    admin_user = User.objects.create_user(
        username='adam_admin_p4',
        email='adam.admin@nexisure.internal',
        role=UserRole.ADMINISTRATOR,
        is_staff=True,
        is_superuser=True,
        password='password123',
    )
    admin_staff = StaffProfile.objects.create(
        user=admin_user,
        staff_code='EMP-ADM-01',
        department='Administration',
        max_claim_approval_limit=Decimal('500000.00'),
    )

    # Vehicles
    vehicle_a = Vehicle.objects.create(
        customer=cust_a,
        registration_number='MH01AB1234',
        vehicle_type=VehicleType.SEDAN,
        make='Honda',
        model='City',
        manufacture_year=2022,
        chassis_number='1HGBH41JXMN109123',
        vehicle_value=Decimal('1200000.00'),
    )
    vehicle_b = Vehicle.objects.create(
        customer=cust_b,
        registration_number='MH12CD5678',
        vehicle_type=VehicleType.SUV,
        make='Hyundai',
        model='Creta',
        manufacture_year=2023,
        chassis_number='KMHCT81EBMU009876',
        vehicle_value=Decimal('1500000.00'),
    )

    # Coverage Plan
    plan, _ = CoveragePlan.objects.get_or_create(
        plan_code=CoveragePlanCode.COMPREHENSIVE,
        defaults={
            'name': 'Comprehensive Vehicle Shield',
            'base_rate_percentage': Decimal('2.850'),
            'description': 'Full comprehensive vehicle protection',
        }
    )

    # Active Policies
    today = date.today()
    policy_a = Policy.objects.create(
        policy_number='POL-2026-CLM01',
        customer=cust_a,
        vehicle=vehicle_a,
        coverage_plan=plan,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=335),
        premium_amount=Decimal('34200.00'),
        deductible_amount=Decimal('2500.00'),
        status=PolicyStatus.ACTIVE,
    )
    policy_b = Policy.objects.create(
        policy_number='POL-2026-CLM02',
        customer=cust_b,
        vehicle=vehicle_b,
        coverage_plan=plan,
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=305),
        premium_amount=Decimal('42750.00'),
        deductible_amount=Decimal('3000.00'),
        status=PolicyStatus.ACTIVE,
    )

    # Expired Policy for boundary testing
    expired_policy = Policy.objects.create(
        policy_number='POL-2024-EXPIRED',
        customer=cust_a,
        vehicle=vehicle_a,
        coverage_plan=plan,
        start_date=today - timedelta(days=730),
        end_date=today - timedelta(days=365),
        premium_amount=Decimal('30000.00'),
        deductible_amount=Decimal('2500.00'),
        status=PolicyStatus.EXPIRED,
    )

    return {
        'cust_a_user': cust_a_user,
        'cust_a': cust_a,
        'cust_b_user': cust_b_user,
        'cust_b': cust_b,
        'handler_user': handler_user,
        'handler_staff': handler_staff,
        'other_handler_user': other_handler_user,
        'other_handler_staff': other_handler_staff,
        'uw_user': uw_user,
        'uw_staff': uw_staff,
        'admin_user': admin_user,
        'admin_staff': admin_staff,
        'vehicle_a': vehicle_a,
        'vehicle_b': vehicle_b,
        'policy_a': policy_a,
        'policy_b': policy_b,
        'expired_policy': expired_policy,
        'plan': plan,
    }


@pytest.mark.django_db
class TestPhase4ClaimsAndServiceRequests:
    """
    Complete Phase 4 Verification covering all 32 requirements from Section 12:
    - Claims lifecycle (1-20)
    - Service Requests (21-29)
    - Security / RBAC / IDOR (30-32)
    """

    # --------------------------------------------------
    # CLAIMS LIFECYCLE (1-20)
    # --------------------------------------------------

    def test_customer_can_file_valid_claim(self, phase4_data):
        """1. Customer can file a valid claim."""
        incident_time = timezone.now() - timedelta(days=2)
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=incident_time,
            incident_location='Western Express Highway, Bandra',
            incident_description='Rear bumper impacted while braking in heavy traffic.',
            estimated_loss_amount=Decimal('15000.00'),
        )
        assert claim.pk is not None
        assert claim.claim_number.startswith('CLM-')
        assert claim.estimated_loss_amount == Decimal('15000.00')
        assert claim.policy == phase4_data['policy_a']
        assert claim.customer == phase4_data['cust_a']

    def test_claim_starts_in_pending(self, phase4_data):
        """2. Claim starts in PENDING."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Linking Road, Khar',
            incident_description='Front headlight cracked by stone projectile.',
            estimated_loss_amount=Decimal('4500.00'),
        )
        assert claim.status == ClaimStatus.PENDING

    def test_new_claim_has_no_handler(self, phase4_data):
        """3. New claim has no handler."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=3),
            incident_location='BKC G Block',
            incident_description='Fender scratch in parking lot.',
            estimated_loss_amount=Decimal('3200.00'),
        )
        assert claim.handler is None

    def test_customer_cannot_choose_handler(self, phase4_data, client):
        """4. Customer cannot choose a handler via filing form/API."""
        client.force_login(phase4_data['cust_a_user'])
        # Customer attempts to pass handler_id in POST
        resp = client.post(
            reverse('claims:create'),
            data={
                'policy_id': phase4_data['policy_a'].pk,
                'incident_date': (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
                'incident_location': 'Worli Sea Face',
                'incident_description': 'Side mirror hit by cyclist.',
                'estimated_loss_amount': '2500',
                'handler': str(phase4_data['handler_staff'].pk),
            }
        )
        assert resp.status_code == 302
        created_claim = Claim.objects.filter(customer=phase4_data['cust_a']).latest('created_at')
        assert created_claim.handler is None
        assert created_claim.status == ClaimStatus.PENDING

    def test_customer_cannot_access_another_customer_claim(self, phase4_data, client):
        """5. Customer cannot access another customer's claim (IDOR check -> 403)."""
        claim_b = ClaimService.file_claim(
            customer=phase4_data['cust_b'],
            policy=phase4_data['policy_b'],
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='FC Road, Pune',
            incident_description='Rear door dented.',
            estimated_loss_amount=Decimal('8000.00'),
        )

        client.force_login(phase4_data['cust_a_user'])
        resp = client.get(reverse('claims:detail', kwargs={'pk': claim_b.pk}))
        assert resp.status_code == 403

    def test_customer_cannot_modify_another_customer_claim(self, phase4_data, client):
        """6. Customer cannot modify another customer's claim."""
        claim_b = ClaimService.file_claim(
            customer=phase4_data['cust_b'],
            policy=phase4_data['policy_b'],
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='Deccan Gymkhana, Pune',
            incident_description='Scratched bumper.',
            estimated_loss_amount=Decimal('6000.00'),
        )

        client.force_login(phase4_data['cust_a_user'])
        # Attempt to upload doc to Claim B
        dummy_file = SimpleUploadedFile("tamper.txt", b"malicious content", content_type="text/plain")
        resp = client.post(
            reverse('claims:document-upload', kwargs={'pk': claim_b.pk}),
            data={'document_file': dummy_file, 'document_title': 'Tamper Attempt'}
        )
        assert resp.status_code == 403
        assert ClaimDocument.objects.filter(claim=claim_b).count() == 0

    def test_handler_can_see_eligible_queue_claims(self, phase4_data, client):
        """7. Handler can see eligible queue claims."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Airport Road, Mumbai',
            incident_description='Bonnet damage from falling tree branch.',
            estimated_loss_amount=Decimal('18000.00'),
        )

        client.force_login(phase4_data['handler_user'])
        resp = client.get(reverse('claims:queue'))
        assert resp.status_code == 200
        assert claim.claim_number in resp.content.decode('utf-8')

    def test_handler_can_self_assign(self, phase4_data):
        """8. Handler can self-assign."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Andheri Kurla Road',
            incident_description='Tail light smashed.',
            estimated_loss_amount=Decimal('5000.00'),
        )

        assigned = ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        assert assigned.handler == phase4_data['handler_staff']

    def test_self_assignment_changes_state_correctly(self, phase4_data):
        """9. Self-assignment changes state correctly to IN_REVIEW."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='Powai Hiranandani',
            incident_description='Windshield chip repair.',
            estimated_loss_amount=Decimal('7500.00'),
        )

        assert claim.status == ClaimStatus.PENDING
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        claim.refresh_from_db()
        assert claim.status == ClaimStatus.IN_REVIEW
        assert claim.handler == phase4_data['handler_staff']

        # Event verified
        event = ClaimEvent.objects.filter(claim=claim, event_type=ClaimEventType.CLAIM_ASSIGNED).first()
        assert event is not None
        assert event.actor == phase4_data['handler_user']

    def test_unauthorized_handler_actions_are_rejected(self, phase4_data, client):
        """10. Unauthorized handler actions are rejected (e.g. adjudicating claim assigned to someone else)."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='Vashi Bridge',
            incident_description='Front bumper misalignment.',
            estimated_loss_amount=Decimal('12000.00'),
        )
        # Assigned to Dan
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        # Dave (other handler) attempts to approve Dan's claim -> 403
        client.force_login(phase4_data['other_handler_user'])
        resp = client.post(
            reverse('claims:decision', kwargs={'pk': claim.pk}),
            data={'action': 'approve', 'settlement_amount': '10000'}
        )
        assert resp.status_code == 403

    def test_authorized_handler_can_review(self, phase4_data):
        """11. Authorized handler can review and log review start."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Juhu Beach Road',
            incident_description='Scratched door panel.',
            estimated_loss_amount=Decimal('4000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        reviewed = ClaimService.review_claim(
            claim=claim,
            handler=phase4_data['handler_staff'],
            notes='Surveyor dispatched for vehicle damage inspection.',
        )
        assert reviewed.status == ClaimStatus.IN_REVIEW
        review_event = ClaimEvent.objects.filter(claim=claim, event_type=ClaimEventType.CLAIM_REVIEW_STARTED).first()
        assert review_event is not None
        assert 'Surveyor dispatched' in review_event.notes

    def test_authorized_handler_can_approve(self, phase4_data):
        """12. Authorized handler can approve within authority limit."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Marine Drive',
            incident_description='Minor collision at traffic stop.',
            estimated_loss_amount=Decimal('22000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        approved = ClaimService.approve_claim(
            claim=claim,
            handler=phase4_data['handler_staff'],
            settlement_amount=Decimal('18500.00'),
            notes='Body shop estimate verified; payout approved.',
        )
        assert approved.status == ClaimStatus.APPROVED
        assert approved.settlement_amount == Decimal('18500.00')

    def test_authorized_handler_can_reject(self, phase4_data):
        """13. Authorized handler can reject with mandatory reason."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Dadar TT Circle',
            incident_description='Engine mechanical wear.',
            estimated_loss_amount=Decimal('8000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        rejected = ClaimService.reject_claim(
            claim=claim,
            handler=phase4_data['handler_staff'],
            rejection_reason='Mechanical breakdown is an excluded loss under section 2.1.',
            notes='Independent surveyor report confirms mechanical seizure without accidental impact.',
        )
        assert rejected.status == ClaimStatus.REJECTED
        assert 'Mechanical breakdown' in rejected.rejection_reason

    def test_customer_cannot_approve_reject(self, phase4_data, client):
        """14. Customer cannot approve or reject claims (must return 403)."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Sion Circle',
            incident_description='Fender dent.',
            estimated_loss_amount=Decimal('3000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        client.force_login(phase4_data['cust_a_user'])
        resp = client.post(
            reverse('claims:decision', kwargs={'pk': claim.pk}),
            data={'action': 'approve', 'settlement_amount': '3000'}
        )
        assert resp.status_code == 403

    def test_invalid_state_transitions_are_rejected(self, phase4_data):
        """15. Invalid state transitions are rejected (e.g. approving a PENDING or already REJECTED claim)."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Kurla West',
            incident_description='Broken indicator.',
            estimated_loss_amount=Decimal('1500.00'),
        )
        # 1. Direct approval of PENDING claim must fail
        with pytest.raises(ServiceValidationError, match="Only claims in IN_REVIEW status can be approved"):
            ClaimService.approve_claim(claim, phase4_data['handler_staff'], Decimal('1500.00'))

        # Move to IN_REVIEW then REJECTED
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        ClaimService.reject_claim(claim, phase4_data['handler_staff'], rejection_reason='Not covered')

        # 2. Re-assigning or approving an already REJECTED claim must fail
        with pytest.raises(ServiceValidationError, match="Only PENDING claims can be self-assigned"):
            ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])

        with pytest.raises(ServiceValidationError, match="Only claims in IN_REVIEW status can be approved"):
            ClaimService.approve_claim(claim, phase4_data['handler_staff'], Decimal('1500.00'))

    def test_claim_decision_is_audited(self, phase4_data):
        """16. Claim decision is audited in AuditService."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Goregaon Link Road',
            incident_description='Rear bumper scratch.',
            estimated_loss_amount=Decimal('5000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        ClaimService.approve_claim(claim, phase4_data['handler_staff'], Decimal('4500.00'))

        log = AuditLog.objects.filter(
            action=AuditAction.CLAIM_APPROVED,
            target_id=str(claim.pk),
        ).first()
        assert log is not None
        assert log.actor == phase4_data['handler_user']
        assert log.details['settlement_amount'] == 4500.0

    def test_claim_documents_respect_ownership_and_rbac(self, phase4_data, client):
        """17. Claim documents respect ownership and RBAC (cross-customer download returns 403)."""
        claim_a = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Chembur Naka',
            incident_description='Scratched door.',
            estimated_loss_amount=Decimal('2000.00'),
        )

        test_file = SimpleUploadedFile("damage.jpg", b"fake image bytes", content_type="image/jpeg")
        doc = ClaimService.add_claim_document(
            claim=claim_a,
            uploaded_by=phase4_data['cust_a_user'],
            document_type=ClaimDocument.DocType.DAMAGE_PHOTO,
            title='Front Door Damage',
            file_obj=test_file,
        )

        # Customer A can access their own document
        client.force_login(phase4_data['cust_a_user'])
        resp_a = client.get(reverse('claims:document-download', kwargs={'doc_pk': doc.pk}))
        assert resp_a.status_code == 200

        # Customer B attempts to download Customer A's document -> 403
        client.force_login(phase4_data['cust_b_user'])
        resp_b = client.get(reverse('claims:document-download', kwargs={'doc_pk': doc.pk}))
        assert resp_b.status_code == 403

    def test_claim_validation_rejects_invalid_dates_and_amounts(self, phase4_data):
        """18. Claim validation rejects invalid dates, future dates, outside term, and negative amounts."""
        # Future date
        with pytest.raises(ServiceValidationError, match="future"):
            ClaimService.file_claim(
                customer=phase4_data['cust_a'],
                policy=phase4_data['policy_a'],
                incident_date=timezone.now() + timedelta(days=2),
                incident_location='Future Road',
                incident_description='Future event',
                estimated_loss_amount=Decimal('1000.00'),
            )

        # Expired policy
        with pytest.raises(ServiceValidationError, match="Policy must be ACTIVE"):
            ClaimService.file_claim(
                customer=phase4_data['cust_a'],
                policy=phase4_data['expired_policy'],
                incident_date=timezone.now() - timedelta(days=1),
                incident_location='Old Road',
                incident_description='Event on expired policy',
                estimated_loss_amount=Decimal('1000.00'),
            )

        # Date falls outside active policy coverage term (policy started 30 days ago)
        with pytest.raises(ServiceValidationError, match="outside policy active term"):
            ClaimService.file_claim(
                customer=phase4_data['cust_a'],
                policy=phase4_data['policy_a'],
                incident_date=timezone.now() - timedelta(days=60),
                incident_location='Highway 4',
                incident_description='Event prior to coverage inception',
                estimated_loss_amount=Decimal('1000.00'),
            )

        # Zero or negative amount
        with pytest.raises(ServiceValidationError, match="greater than zero"):
            ClaimService.file_claim(
                customer=phase4_data['cust_a'],
                policy=phase4_data['policy_a'],
                incident_date=timezone.now() - timedelta(days=1),
                incident_location='Valid Location',
                incident_description='Valid description',
                estimated_loss_amount=Decimal('0.00'),
            )

    def test_duplicate_settlement_prevented(self, phase4_data):
        """19. Duplicate settlement is prevented if settlement exists."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Kala Ghoda',
            incident_description='Mirror shattered.',
            estimated_loss_amount=Decimal('5000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        ClaimService.approve_claim(claim, phase4_data['handler_staff'], Decimal('4000.00'))

        # First settlement succeeds
        ClaimService.settle_claim(claim, phase4_data['handler_user'])
        claim.refresh_from_db()
        assert claim.status == ClaimStatus.SETTLED

        # Second settlement attempt must be rejected
        with pytest.raises(ServiceValidationError, match="Duplicate settlement is prohibited"):
            ClaimService.settle_claim(claim, phase4_data['handler_user'])

    def test_approved_claim_settlement_constraints(self, phase4_data):
        """20. Approved claim settlement is correctly constrained."""
        claim = ClaimService.file_claim(
            customer=phase4_data['cust_a'],
            policy=phase4_data['policy_a'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Colaba Causeway',
            incident_description='Dent repair.',
            estimated_loss_amount=Decimal('10000.00'),
        )
        ClaimService.self_assign_claim(claim, phase4_data['handler_staff'])
        ClaimService.approve_claim(claim, phase4_data['handler_staff'], Decimal('8000.00'))

        # Settle exceeding authorized approval amount must fail
        with pytest.raises(ServiceValidationError, match="cannot exceed authorized approval amount"):
            ClaimService.settle_claim(claim, phase4_data['handler_user'], settlement_amount=Decimal('9000.00'))

        # Non-positive payout must fail
        with pytest.raises(ServiceValidationError, match="greater than zero"):
            ClaimService.settle_claim(claim, phase4_data['handler_user'], settlement_amount=Decimal('-500.00'))

        # Customer attempting settlement must fail
        with pytest.raises(ServiceValidationError, match="Only authorized Claims Handlers"):
            ClaimService.settle_claim(claim, phase4_data['cust_a_user'])

    # --------------------------------------------------
    # SERVICE REQUESTS (21-29)
    # --------------------------------------------------

    def test_customer_can_create_request_for_own_resource(self, phase4_data):
        """21. Customer can create a request for their own resource."""
        srv = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_a'],
            request_type=ServiceRequestType.ADDRESS_UPDATE,
            title='Update Primary Garaging Address',
            description='Moved residence to Bandra West, Mumbai 400050.',
            policy=phase4_data['policy_a'],
        )
        assert srv.pk is not None
        assert srv.status == ServiceRequestStatus.SUBMITTED
        assert srv.customer == phase4_data['cust_a']
        assert srv.policy == phase4_data['policy_a']

    def test_customer_cannot_create_request_for_another_customer_resource(self, phase4_data, client):
        """22. Customer cannot create a request for another customer's resource."""
        # 1. Service layer check
        with pytest.raises(ServiceValidationError, match="You may only file service requests against your own policies"):
            ServiceRequestService.create_service_request(
                customer=phase4_data['cust_a'],
                request_type=ServiceRequestType.POLICY_SERVICE,
                title='Unauthorized Service Request',
                description='Attempting to service Bob policy',
                policy=phase4_data['policy_b'],
            )

        # 2. View layer check -> 403
        client.force_login(phase4_data['cust_a_user'])
        resp = client.post(
            reverse('service_requests:create'),
            data={
                'policy_id': str(phase4_data['policy_b'].pk),
                'request_type': ServiceRequestType.POLICY_SERVICE,
                'title': 'Intrusion Test',
                'description': 'Trying to file against Customer B policy',
            }
        )
        assert resp.status_code == 403

    def test_customer_can_view_own_request(self, phase4_data, client):
        """23. Customer can view their own request."""
        srv = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_a'],
            request_type=ServiceRequestType.DOCUMENT_REQUEST,
            title='Request Tax Invoice & Certificate',
            description='Please issue certificate for fiscal tax filing.',
            policy=phase4_data['policy_a'],
        )

        client.force_login(phase4_data['cust_a_user'])
        resp = client.get(reverse('service_requests:detail', kwargs={'pk': srv.pk}))
        assert resp.status_code == 200
        assert srv.request_number in resp.content.decode('utf-8')

    def test_customer_cannot_view_another_customer_request(self, phase4_data, client):
        """24. Customer cannot view another customer's request (IDOR -> 403)."""
        srv_b = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_b'],
            request_type=ServiceRequestType.POLICY_SERVICE,
            title='Bob confidential request',
            description='Confidential inquiry details',
            policy=phase4_data['policy_b'],
        )

        client.force_login(phase4_data['cust_a_user'])
        resp = client.get(reverse('service_requests:detail', kwargs={'pk': srv_b.pk}))
        assert resp.status_code == 403

    def test_authorized_staff_can_process_request(self, phase4_data, client):
        """25. Authorized staff can process a request."""
        srv = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_a'],
            request_type=ServiceRequestType.POLICY_RENEWAL,
            title='Early Renewal Inquiry',
            description='Inquiring about 3-year multi-year renewal options.',
            policy=phase4_data['policy_a'],
        )

        client.force_login(phase4_data['uw_user'])
        resp = client.post(
            reverse('service_requests:update_status', kwargs={'pk': srv.pk}),
            data={'status': ServiceRequestStatus.IN_PROGRESS, 'resolution_notes': 'Underwriter review initiated.'}
        )
        assert resp.status_code == 302
        srv.refresh_from_db()
        assert srv.status == ServiceRequestStatus.IN_PROGRESS

        # Resolve
        client.post(
            reverse('service_requests:update_status', kwargs={'pk': srv.pk}),
            data={'status': ServiceRequestStatus.RESOLVED, 'resolution_notes': 'Renewal terms quote generated.'}
        )
        srv.refresh_from_db()
        assert srv.status == ServiceRequestStatus.RESOLVED
        assert srv.resolved_at is not None

    def test_service_request_invalid_state_transitions_rejected(self, phase4_data):
        """26. Invalid state transitions are rejected on service requests."""
        srv = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_a'],
            request_type=ServiceRequestType.ADDRESS_UPDATE,
            title='Address Change',
            description='New flat address.',
            policy=phase4_data['policy_a'],
        )
        # Move to RESOLVED
        ServiceRequestService.update_status(srv, phase4_data['uw_user'], ServiceRequestStatus.RESOLVED)

        # Terminal state check: cannot update resolved request
        with pytest.raises(ServiceValidationError, match="terminal state"):
            ServiceRequestService.update_status(srv, phase4_data['uw_user'], ServiceRequestStatus.IN_PROGRESS)

    def test_immutable_policy_financial_fields_protected(self, phase4_data):
        """27. Immutable policy financial fields cannot be changed through a service request."""
        # Attempting to tamper with premium_amount or idv via change_payload must be rejected
        with pytest.raises(ServiceValidationError, match="Cannot modify immutable financial policy field"):
            ServiceRequestService.create_service_request(
                customer=phase4_data['cust_a'],
                request_type=ServiceRequestType.ENDORSEMENT,
                title='Unauthorized Premium Modification',
                description='Attempting to lower premium',
                policy=phase4_data['policy_a'],
                change_payload={'premium_amount': '100.00', 'city': 'Pune'},
            )

        with pytest.raises(ServiceValidationError, match="Cannot modify immutable financial policy field"):
            ServiceRequestService.create_service_request(
                customer=phase4_data['cust_a'],
                request_type=ServiceRequestType.ENDORSEMENT,
                title='Unauthorized IDV Modification',
                description='Attempting to alter IDV',
                policy=phase4_data['policy_a'],
                change_payload={'vehicle_value': '5000000.00'},
            )

    def test_service_request_lifecycle_actions_are_audited(self, phase4_data):
        """28. Service-request lifecycle actions are audited."""
        srv = ServiceRequestService.create_service_request(
            customer=phase4_data['cust_a'],
            request_type=ServiceRequestType.DOCUMENT_REQUEST,
            title='Tax Certificate Request',
            description='Requesting annual policy document.',
            policy=phase4_data['policy_a'],
        )

        create_log = AuditLog.objects.filter(
            action=AuditAction.SERVICE_REQUEST_CREATED,
            target_id=str(srv.pk),
        ).first()
        assert create_log is not None

        ServiceRequestService.update_status(
            service_request=srv,
            staff_user=phase4_data['uw_user'],
            new_status=ServiceRequestStatus.RESOLVED,
            resolution_notes='Certificate generated and sent.',
        )

        resolve_log = AuditLog.objects.filter(
            action=AuditAction.SERVICE_REQUEST_RESOLVED,
            target_id=str(srv.pk),
        ).first()
        assert resolve_log is not None
        assert resolve_log.actor == phase4_data['uw_user']

    def test_csrf_protection_on_state_changing_endpoints(self, phase4_data):
        """29. CSRF protection is enforced on state-changing endpoints."""
        from django.test import Client
        enforcing_client = Client(enforce_csrf_checks=True)
        enforcing_client.force_login(phase4_data['cust_a_user'])

        # File claim without CSRF token -> 403
        resp = enforcing_client.post(
            reverse('claims:create'),
            data={'policy_id': str(phase4_data['policy_a'].pk)}
        )
        assert resp.status_code == 403

        # Create service request without CSRF token -> 403
        resp_srv = enforcing_client.post(
            reverse('service_requests:create'),
            data={'title': 'No CSRF Token'}
        )
        assert resp_srv.status_code == 403

    # --------------------------------------------------
    # SECURITY & RBAC (30-32)
    # --------------------------------------------------

    def test_unauthenticated_protected_requests_redirect_to_login(self, phase4_data, client):
        """30. Unauthenticated protected requests redirect to authentication."""
        client.logout()

        # Claim queue requires claims handler
        resp_queue = client.get(reverse('claims:queue'))
        assert resp_queue.status_code == 302
        assert '/login/' in resp_queue['Location']

        # File claim requires customer login
        resp_file = client.get(reverse('claims:create'))
        assert resp_file.status_code == 302
        assert '/login/' in resp_file['Location']

        # Service request requires login
        resp_srv = client.get(reverse('service_requests:list'))
        assert resp_srv.status_code == 302
        assert '/login/' in resp_srv['Location']

    def test_cross_customer_idor_returns_403_or_404(self, phase4_data, client):
        """31. Cross-customer IDOR attempts return 403 according to project convention."""
        claim_b = ClaimService.file_claim(
            customer=phase4_data['cust_b'],
            policy=phase4_data['policy_b'],
            incident_date=timezone.now() - timedelta(days=1),
            incident_location='Shivajinagar, Pune',
            incident_description='Bumper crack.',
            estimated_loss_amount=Decimal('4000.00'),
        )

        client.force_login(phase4_data['cust_a_user'])

        # Detail view cross-access
        resp_detail = client.get(reverse('claims:detail', kwargs={'pk': claim_b.pk}))
        assert resp_detail.status_code in (403, 404)

    def test_role_restrictions_enforced_serverside(self, phase4_data, client):
        """32. Role restrictions are enforced server-side (e.g. Underwriter cannot access Claims queue)."""
        # Underwriter attempts to access Claims queue -> 403
        client.force_login(phase4_data['uw_user'])
        resp_uw = client.get(reverse('claims:queue'))
        assert resp_uw.status_code == 403

        # Customer attempts to access Claims queue -> 403
        client.force_login(phase4_data['cust_a_user'])
        resp_cust = client.get(reverse('claims:queue'))
        assert resp_cust.status_code == 403
