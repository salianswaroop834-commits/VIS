import pytest
from decimal import Decimal
from django.core.management import call_command
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from staff.models import StaffProfile
from vehicles.models import Vehicle
from quotations.models import CoveragePlan, QuotationDraft
from policies.models import Policy, PolicyStatus
from claims.models import Claim, ClaimStatus
from service_requests.models import ServiceRequest
from predictions.models import ModelVersion, ModelLifecycleStatus
from rag.models import KnowledgeDocument
from audit.models import AuditLog


@pytest.mark.django_db
class TestPhase13DemoAndFinalValidation:
    """
    Phase 13: Final Demo, Pitch, and System Validation Suite.
    - Verifies automated seed_demo_data command execution
    - Validates demo user credential readiness
    - Verifies end-to-end domain entity seeding
    - Confirms MLOps active registry and RAG knowledge corpus readiness
    """

    def test_demo_seed_execution_and_entity_integrity(self):
        # 1. Execute seed command
        call_command('seed_demo_data')

        # 2. Verify Demo Users & Roles
        admin_user = User.objects.get(email='admin@nexisure.test')
        assert admin_user.role == UserRole.ADMINISTRATOR
        assert admin_user.is_staff is True
        assert admin_user.is_superuser is True
        assert admin_user.check_password('DemoAdmin@2026') is True
        assert StaffProfile.objects.filter(user=admin_user).exists()

        uw_user = User.objects.get(email='underwriter@nexisure.test')
        assert uw_user.role == UserRole.UNDERWRITER
        assert uw_user.is_staff is True
        assert uw_user.check_password('DemoStaff@2026') is True
        assert StaffProfile.objects.filter(user=uw_user).exists()

        ch_user = User.objects.get(email='handler@nexisure.test')
        assert ch_user.role == UserRole.CLAIMS_HANDLER
        assert ch_user.is_staff is True
        assert ch_user.check_password('DemoStaff@2026') is True
        ch_profile = StaffProfile.objects.get(user=ch_user)
        assert ch_profile.max_claim_approval_limit == Decimal('50000.00')

        cust_user = User.objects.get(email='customer@nexisure.test')
        assert cust_user.role == UserRole.CUSTOMER
        assert cust_user.check_password('DemoCust@2026') is True
        cust_profile = CustomerProfile.objects.get(user=cust_user)
        assert cust_profile.customer_code == 'CUST-DEMO-01'

        # 3. Verify Seeded Domain Entities
        assert Vehicle.objects.filter(customer=cust_profile).count() >= 2
        assert QuotationDraft.objects.filter(customer=cust_profile).exists()
        assert Policy.objects.filter(customer=cust_profile, status=PolicyStatus.ACTIVE).exists()
        assert Claim.objects.filter(customer=cust_profile, status=ClaimStatus.PENDING).exists()
        assert ServiceRequest.objects.filter(customer=cust_profile).exists()

        # 4. Verify MLOps Registry
        assert ModelVersion.objects.filter(is_active_for_inference=True).count() >= 2

        # 5. Verify RAG Knowledge Documents
        assert KnowledgeDocument.objects.filter(is_approved_for_rag=True).count() >= 3

        # 6. Verify Audit Ledger Entry
        assert AuditLog.objects.filter(action='SYSTEM_DEMO_SEEDED').exists()

    def test_demo_idempotence(self):
        """Executing seed_demo_data multiple times is safe and idempotent."""
        call_command('seed_demo_data')
        admin_count_1 = User.objects.filter(email='admin@nexisure.test').count()
        call_command('seed_demo_data')
        admin_count_2 = User.objects.filter(email='admin@nexisure.test').count()
        assert admin_count_1 == admin_count_2 == 1
