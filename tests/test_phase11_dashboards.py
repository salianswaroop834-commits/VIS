import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.staff.models import StaffProfile
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.quotations.models import CoveragePlan, CoveragePlanCode
from apps.policies.models import Policy, PolicyStatus
from apps.claims.models import Claim, ClaimStatus


@pytest.mark.django_db
class TestPhase11RoleBasedDashboards:
    """
    Test suite verifying Phase 11 role-based dashboards:
    - Customer Dashboard with renewal alerts & asset lists
    - Underwriter Dashboard with portfolio volume & search
    - Claims Handler Dashboard with shared queue & approval limits
    - Administrator Operations & Governance Dashboard
    - Strict RBAC authorization barriers
    """

    @pytest.fixture
    def customer_user(self):
        user = User.objects.create_user(
            username='cust_dash',
            email='cust_dash@nexisure.test',
            first_name='David',
            last_name='Miller',
            role=UserRole.CUSTOMER,
        )
        CustomerProfile.objects.create(
            user=user,
            customer_code='CUST-DASH-01',
            date_of_birth=date(1988, 3, 10),
            address_line='742 Evergreen Terrace',
            city='Springfield',
            postal_code='97477',
        )
        return user

    @pytest.fixture
    def underwriter_user(self):
        user = User.objects.create_user(
            username='uw_dash',
            email='uw_dash@nexisure.test',
            first_name='Sarah',
            last_name='Jenkins',
            role=UserRole.UNDERWRITER,
            is_staff=True,
        )
        StaffProfile.objects.create(
            user=user,
            staff_code='UW-DASH-01',
            department='Underwriting',
        )
        return user

    @pytest.fixture
    def claims_handler_user(self):
        user = User.objects.create_user(
            username='ch_dash',
            email='ch_dash@nexisure.test',
            first_name='Marcus',
            last_name='Vance',
            role=UserRole.CLAIMS_HANDLER,
            is_staff=True,
        )
        StaffProfile.objects.create(
            user=user,
            staff_code='CH-DASH-01',
            department='Claims',
            max_claim_approval_limit=Decimal('5000.00'),
        )
        return user

    @pytest.fixture
    def admin_user(self):
        user = User.objects.create_user(
            username='admin_dash',
            email='admin_dash@nexisure.test',
            first_name='Eleanor',
            last_name='Roosevelt',
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )
        StaffProfile.objects.create(
            user=user,
            staff_code='ADM-DASH-01',
            department='Executive Administration',
            max_claim_approval_limit=Decimal('100000.00'),
        )
        return user

    @pytest.fixture
    def sample_policy(self, customer_user, underwriter_user):
        plan, _ = CoveragePlan.objects.get_or_create(
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            defaults={'name': 'Comprehensive', 'base_rate_percentage': Decimal('3.50')}
        )
        vehicle = Vehicle.objects.create(
            customer=customer_user.customer_profile,
            registration_number='WA09DASH11',
            make='Toyota',
            model='RAV4',
            manufacture_year=2022,
            chassis_number='CHAS-DASH-9911',
            vehicle_type=VehicleType.SUV,
            fuel_type=FuelType.HYBRID,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('32000.00'),
        )
        policy = Policy.objects.create(
            policy_number='POL-2026-DASH01',
            customer=customer_user.customer_profile,
            vehicle=vehicle,
            coverage_plan=plan,
            underwriter=underwriter_user.staff_profile,
            premium_amount=Decimal('1120.00'),
            deductible_amount=Decimal('500.00'),
            duration_years=1,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() + timedelta(days=305),
            status=PolicyStatus.ACTIVE,
        )
        return policy

    def test_customer_dashboard_renders_active_policies_and_kpis(self, client, customer_user, sample_policy):
        url = reverse('customers:dashboard')
        client.force_login(customer_user)
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Welcome back, David' in content
        assert sample_policy.policy_number in content
        assert 'WA09DASH11' in content
        assert 'Active Policies' in content

    def test_customer_dashboard_renewal_alert_for_expiring_policy(self, client, customer_user, sample_policy):
        # Update policy end date to 15 days from now (within 30 days renewal threshold)
        sample_policy.end_date = date.today() + timedelta(days=15)
        sample_policy.save(update_fields=['end_date'])

        url = reverse('customers:dashboard')
        client.force_login(customer_user)
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Renewal Alert' in content
        assert 'expiring within 30 days' in content

    def test_underwriter_dashboard_renders_portfolio_and_metrics(self, client, underwriter_user, sample_policy):
        url = reverse('staff:underwriter-dashboard')
        client.force_login(underwriter_user)
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Underwriting Portfolio' in content or 'Active Policies' in content
        assert sample_policy.policy_number in content
        assert '₹1,120' in content or '1120' in content or '$1,120' in content

    def test_claims_handler_dashboard_renders_queues_and_limits(self, client, claims_handler_user, sample_policy):
        from django.utils import timezone
        # Seed 1 pending claim and 1 in-review claim
        Claim.objects.create(
            claim_number='CLM-2026-PEND01',
            policy=sample_policy,
            customer=sample_policy.customer,
            incident_date=timezone.now() - timedelta(days=2),
            incident_location='Highway 101',
            incident_description='Fender bender',
            estimated_loss_amount=Decimal('1200.00'),
            status=ClaimStatus.PENDING,
            handler=None,
        )
        Claim.objects.create(
            claim_number='CLM-2026-REV01',
            policy=sample_policy,
            customer=sample_policy.customer,
            incident_date=timezone.now() - timedelta(days=5),
            incident_location='Downtown',
            incident_description='Broken windshield',
            estimated_loss_amount=Decimal('650.00'),
            status=ClaimStatus.IN_REVIEW,
            handler=claims_handler_user.staff_profile,
        )

        url = reverse('staff:claims-handler-dashboard')
        client.force_login(claims_handler_user)
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Claims Queue & Adjudication Desk' in content
        assert 'Pending in Shared Queue' in content
        assert '₹5000' in content or '₹5,000' in content or '$5000' in content or '$5,000' in content  # Authority approval limit
        assert 'CLM-2026-REV01' in content

    def test_admin_dashboard_renders_operations_and_governance(self, client, admin_user, sample_policy):
        url = reverse('staff:admin-dashboard')
        client.force_login(admin_user)
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Executive Administration' in content
        assert 'System Governance & Operations Command' in content
        assert 'Total Written Premium' in content
        assert 'Loss Ratio' in content
        assert 'MLOps Model Registry' in content

    def test_role_enforcement_on_dashboards(self, client, customer_user, underwriter_user):
        # Customer attempting to access Admin Dashboard -> 403 Forbidden
        client.force_login(customer_user)
        resp_cust = client.get(reverse('staff:admin-dashboard'))
        assert resp_cust.status_code == 403

        # Underwriter attempting to access Claims Handler Dashboard -> 403 Forbidden
        client.force_login(underwriter_user)
        resp_uw = client.get(reverse('staff:claims-handler-dashboard'))
        assert resp_uw.status_code == 403

    def test_customer_dashboard_empty_states(self, client):
        """Customer with no assets sees proper empty states without errors."""
        new_user = User.objects.create_user(
            username='cust_empty',
            email='empty@nexisure.test',
            role=UserRole.CUSTOMER,
        )
        CustomerProfile.objects.create(
            user=new_user,
            customer_code='CUST-EMPTY-01',
            date_of_birth=date(1995, 1, 1),
            address_line='1 Empty St',
            city='Pune',
            postal_code='411001',
        )
        client.force_login(new_user)
        url = reverse('customers:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'No active policies found' in content
        assert 'No claims on record' in content
        assert '0' in content

    def test_claims_handler_empty_queue(self, client, claims_handler_user):
        """Claims handler with no claims sees proper empty queue state."""
        client.force_login(claims_handler_user)
        url = reverse('staff:claims-handler-dashboard')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Shared queue is empty' in content
        assert 'You currently have no in-review claims assigned' in content

    def test_currency_inr_consistency_across_dashboards(self, client, customer_user, underwriter_user, claims_handler_user, admin_user, sample_policy):
        """All role-based dashboards render financial numbers with INR (₹) symbol."""
        # Customer dashboard
        client.force_login(customer_user)
        resp_cust = client.get(reverse('customers:dashboard'))
        assert '₹' in resp_cust.content.decode('utf-8')

        # Underwriter dashboard
        client.force_login(underwriter_user)
        resp_uw = client.get(reverse('staff:underwriter-dashboard'))
        assert '₹' in resp_uw.content.decode('utf-8')

        # Claims handler dashboard
        client.force_login(claims_handler_user)
        resp_ch = client.get(reverse('staff:claims-handler-dashboard'))
        assert '₹' in resp_ch.content.decode('utf-8')

        # Admin dashboard
        client.force_login(admin_user)
        resp_adm = client.get(reverse('staff:admin-dashboard'))
        assert '₹' in resp_adm.content.decode('utf-8')

