import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import UserRole
from policies.models import Policy, PolicyStatus
from quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from customers.models import CustomerProfile
from vehicles.models import Vehicle, VehicleType, FuelType
from claims.models import Claim, ClaimStatus
from service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from analytics import selectors
from analytics.services.portfolio_analytics_service import PortfolioAnalyticsService

User = get_user_model()


@pytest.fixture
def test_users(db):
    customer_user = User.objects.create_user(
        username='customer_phase6',
        email='customer_phase6@nexisure.test',
        password='TestPassword123!',
        role=UserRole.CUSTOMER,
        email_verified=True,
    )
    CustomerProfile.objects.create(
        user=customer_user,
        customer_code='CUST-P6-001',
        address_line='123 Test Street',
        city='Bengaluru',
    )

    underwriter_user = User.objects.create_user(
        username='underwriter_phase6',
        email='underwriter_phase6@nexisure.test',
        password='TestPassword123!',
        role=UserRole.UNDERWRITER,
        email_verified=True,
        is_staff=True,
    )

    claims_handler_user = User.objects.create_user(
        username='handler_phase6',
        email='handler_phase6@nexisure.test',
        password='TestPassword123!',
        role=UserRole.CLAIMS_HANDLER,
        email_verified=True,
        is_staff=True,
    )

    admin_user = User.objects.create_user(
        username='admin_phase6',
        email='admin_phase6@nexisure.test',
        password='TestPassword123!',
        role=UserRole.ADMINISTRATOR,
        email_verified=True,
        is_staff=True,
        is_superuser=True,
    )

    return {
        'customer': customer_user,
        'underwriter': underwriter_user,
        'handler': claims_handler_user,
        'admin': admin_user,
    }


@pytest.fixture
def sample_portfolio_data(db, test_users):
    customer = test_users['customer'].customer_profile

    # Coverage plans
    plan_comp, _ = CoveragePlan.objects.get_or_create(
        plan_code=CoveragePlanCode.COMPREHENSIVE,
        defaults={
            'name': 'Comprehensive Tier',
            'description': 'Full coverage',
            'base_rate_percentage': Decimal('2.850'),
            'standard_deductible': Decimal('1000.00'),
        }
    )
    plan_tp, _ = CoveragePlan.objects.get_or_create(
        plan_code=CoveragePlanCode.THIRD_PARTY,
        defaults={
            'name': 'Third-Party Tier',
            'description': 'Liability only',
            'base_rate_percentage': Decimal('1.500'),
            'standard_deductible': Decimal('1000.00'),
        }
    )

    # Vehicles
    v1 = Vehicle.objects.create(
        customer=customer,
        registration_number='KA01AB1234',
        chassis_number='CHASSIS-P6-001',
        vehicle_type=VehicleType.SEDAN,
        fuel_type=FuelType.PETROL,
        make='Honda',
        model='City',
        manufacture_year=2021,
        vehicle_value=Decimal('850000.00'),
    )
    v2 = Vehicle.objects.create(
        customer=customer,
        registration_number='KA02CD5678',
        chassis_number='CHASSIS-P6-002',
        vehicle_type=VehicleType.SUV,
        fuel_type=FuelType.DIESEL,
        make='Hyundai',
        model='Creta',
        manufacture_year=2022,
        vehicle_value=Decimal('1200000.00'),
    )

    # Policies
    today = timezone.now().date()
    p1 = Policy.objects.create(
        policy_number='POL-P6-001',
        customer=customer,
        vehicle=v1,
        coverage_plan=plan_comp,
        status=PolicyStatus.ACTIVE,
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=305),
        duration_years=1,
        premium_amount=Decimal('22000.00'),
        deductible_amount=Decimal('2000.00'),
    )
    p2 = Policy.objects.create(
        policy_number='POL-P6-002',
        customer=customer,
        vehicle=v2,
        coverage_plan=plan_tp,
        status=PolicyStatus.ACTIVE,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=335),
        duration_years=1,
        premium_amount=Decimal('8000.00'),
        deductible_amount=Decimal('1000.00'),
    )
    p3 = Policy.objects.create(
        policy_number='POL-P6-003',
        customer=customer,
        vehicle=v1,
        coverage_plan=plan_comp,
        status=PolicyStatus.EXPIRED,
        start_date=today - timedelta(days=400),
        end_date=today - timedelta(days=35),
        duration_years=1,
        premium_amount=Decimal('20000.00'),
        deductible_amount=Decimal('2000.00'),
    )

    # Claims
    c1 = Claim.objects.create(
        claim_number='CLM-P6-001',
        policy=p1,
        customer=customer,
        incident_date=timezone.now() - timedelta(days=15),
        incident_location='Bengaluru Central',
        incident_description='Minor bumper scratch',
        status=ClaimStatus.APPROVED,
        estimated_loss_amount=Decimal('15000.00'),
        settlement_amount=Decimal('12000.00'),
    )
    c2 = Claim.objects.create(
        claim_number='CLM-P6-002',
        policy=p1,
        customer=customer,
        incident_date=timezone.now() - timedelta(days=5),
        incident_location='Outer Ring Road',
        incident_description='Tail light damage',
        status=ClaimStatus.PENDING,
        estimated_loss_amount=Decimal('8000.00'),
        settlement_amount=Decimal('0.00'),
    )

    # Service Request
    sr1 = ServiceRequest.objects.create(
        request_number='SR-P6-001',
        policy=p1,
        customer=customer,
        request_type=ServiceRequestType.ENDORSEMENT,
        status=ServiceRequestStatus.SUBMITTED,
        title='Update contact address',
        description='Requesting new correspondence address',
    )

    return {
        'customer': customer,
        'vehicles': [v1, v2],
        'policies': [p1, p2, p3],
        'claims': [c1, c2],
        'service_requests': [sr1],
    }


@pytest.mark.django_db
class TestPhase6PortfolioAnalyticsSelectors:

    def test_empty_database_graceful_handling(self):
        """Selectors must not throw ZeroDivisionError or return None when DB is completely empty."""
        metrics = selectors.get_policy_portfolio_metrics()
        assert metrics['total_policies'] == 0
        assert metrics['active_policies'] == 0
        assert metrics['total_premium'] == Decimal('0.00')
        assert metrics['avg_premium'] == Decimal('0.00')

        dist = selectors.get_policy_status_distribution()
        assert dist == []

        plans = selectors.get_policy_plan_distribution()
        assert plans == []

        ts = selectors.get_policy_time_series()
        assert ts == []

        cust_metrics = selectors.get_customer_portfolio_metrics()
        assert cust_metrics['total_customers'] == 0
        assert cust_metrics['customers_with_active_policies'] == 0

        veh_metrics = selectors.get_vehicle_portfolio_metrics()
        assert veh_metrics['total_vehicles'] == 0
        assert veh_metrics['avg_idv'] == Decimal('0.00')

        claim_metrics = selectors.get_claim_portfolio_metrics()
        assert claim_metrics['total_claims'] == 0
        assert claim_metrics['claim_frequency_pct'] == 0.0

        fin_metrics = selectors.get_financial_portfolio_metrics()
        assert fin_metrics['gross_premium_written'] == Decimal('0.00')
        assert fin_metrics['loss_ratio_pct'] == 0.0

    def test_policy_kpi_calculations(self, sample_portfolio_data):
        """Verifies policy counts, status breakdown, and financial averages."""
        metrics = selectors.get_policy_portfolio_metrics()
        assert metrics['total_policies'] == 3
        assert metrics['active_policies'] == 2
        assert metrics['expired_policies'] == 1
        assert metrics['cancelled_policies'] == 0
        assert metrics['total_premium'] == Decimal('50000.00')  # 22k + 8k + 20k
        assert metrics['avg_premium'] == round(Decimal('50000.00') / 3, 2)
        assert metrics['term_distribution'].get(1) == 3

    def test_policy_status_distribution(self, sample_portfolio_data):
        """Verifies policy status breakdown and percentage calculation."""
        dist = selectors.get_policy_status_distribution()
        assert len(dist) == 2
        status_map = {d['status']: d for d in dist}
        assert status_map[PolicyStatus.ACTIVE]['count'] == 2
        assert status_map[PolicyStatus.ACTIVE]['percentage'] == pytest.approx(66.67, 0.1)
        assert status_map[PolicyStatus.EXPIRED]['count'] == 1
        assert status_map[PolicyStatus.EXPIRED]['percentage'] == pytest.approx(33.33, 0.1)

    def test_policy_plan_distribution(self, sample_portfolio_data):
        """Verifies plan volume and percentages."""
        plans = selectors.get_policy_plan_distribution()
        assert len(plans) == 2
        plan_codes = [p['plan_code'] for p in plans]
        assert CoveragePlanCode.COMPREHENSIVE in plan_codes
        assert CoveragePlanCode.THIRD_PARTY in plan_codes

    def test_policy_time_series_aggregation(self, sample_portfolio_data):
        """Verifies monthly time series aggregation returns valid months and counts."""
        series = selectors.get_policy_time_series()
        assert len(series) > 0
        for item in series:
            assert 'month' in item
            assert item['policy_count'] >= 1
            assert item['total_premium'] > Decimal('0.00')

    def test_customer_portfolio_metrics(self, sample_portfolio_data):
        """Verifies customer counts and active policy association."""
        metrics = selectors.get_customer_portfolio_metrics()
        assert metrics['total_customers'] >= 1
        assert metrics['customers_with_active_policies'] >= 1

    def test_vehicle_portfolio_metrics(self, sample_portfolio_data):
        """Verifies vehicle inventory, fuel, and vehicle category distributions."""
        v_metrics = selectors.get_vehicle_portfolio_metrics()
        assert v_metrics['total_vehicles'] == 2
        assert v_metrics['active_vehicles'] == 2
        assert v_metrics['vehicle_type_distribution'].get(VehicleType.SEDAN) == 1
        assert v_metrics['vehicle_type_distribution'].get(VehicleType.SUV) == 1
        assert v_metrics['fuel_type_distribution'].get(FuelType.PETROL) == 1
        assert v_metrics['fuel_type_distribution'].get(FuelType.DIESEL) == 1
        assert v_metrics['avg_idv'] == Decimal('1025000.00')

    def test_claim_portfolio_metrics_and_loss_ratio(self, sample_portfolio_data):
        """Verifies claim metrics, loss totals, authorized settlement amounts, and loss ratio."""
        claim_metrics = selectors.get_claim_portfolio_metrics()
        assert claim_metrics['total_claims'] == 2
        assert claim_metrics['approved_claims'] == 1
        assert claim_metrics['pending_claims'] == 1
        assert claim_metrics['total_estimated_loss'] == Decimal('23000.00')
        assert claim_metrics['total_settlement_authorized'] == Decimal('12000.00')
        assert claim_metrics['claim_frequency_pct'] == 100.0  # 2 claims / 2 active policies * 100

        fin = selectors.get_financial_portfolio_metrics()
        assert fin['gross_premium_written'] == Decimal('30000.00')  # 22k + 8k active policies
        assert fin['incurred_settlements'] == Decimal('12000.00')
        assert fin['loss_ratio_pct'] == 40.0  # 12000 / 30000 * 100

    def test_claim_status_distribution(self, sample_portfolio_data):
        """Verifies claim status percentage breakdown."""
        dist = selectors.get_claim_status_distribution()
        assert len(dist) == 2
        status_map = {d['status']: d['count'] for d in dist}
        assert status_map[ClaimStatus.APPROVED] == 1
        assert status_map[ClaimStatus.PENDING] == 1

    def test_claim_time_series(self, sample_portfolio_data):
        """Verifies claim time series returns monthly filing counts and loss totals."""
        series = selectors.get_claim_time_series()
        assert len(series) > 0
        assert series[0]['claim_count'] >= 1
        assert 'total_loss' in series[0]

    def test_service_request_metrics(self, sample_portfolio_data):
        """Verifies service request aggregations by type and status."""
        sr_metrics = selectors.get_service_request_metrics()
        assert sr_metrics['total_requests'] == 1
        assert sr_metrics['requests_by_type'].get(ServiceRequestType.ENDORSEMENT) == 1
        assert sr_metrics['requests_by_status'].get(ServiceRequestStatus.SUBMITTED) == 1


@pytest.mark.django_db
class TestPhase6FilteringAndServiceLayer:

    def test_date_range_filtering(self, sample_portfolio_data):
        """Verifies filtering by start and end date ranges."""
        today = timezone.now().date()
        # Filter for policies started in last 45 days (should only include p2)
        filtered = PortfolioAnalyticsService.get_policy_portfolio_metrics({
            'start_date': today - timedelta(days=45),
            'end_date': today,
        })
        assert filtered['total_policies'] == 1
        assert filtered['total_premium'] == Decimal('8000.00')

    def test_policy_status_filtering(self, sample_portfolio_data):
        """Verifies filtering by policy status."""
        filtered = PortfolioAnalyticsService.get_policy_portfolio_metrics({
            'status': PolicyStatus.EXPIRED,
        })
        assert filtered['total_policies'] == 1
        assert filtered['total_premium'] == Decimal('20000.00')

    def test_plan_code_filtering(self, sample_portfolio_data):
        """Verifies filtering by coverage plan."""
        filtered = PortfolioAnalyticsService.get_policy_portfolio_metrics({
            'plan_code': CoveragePlanCode.THIRD_PARTY,
        })
        assert filtered['total_policies'] == 1
        assert filtered['total_premium'] == Decimal('8000.00')

    def test_live_portfolio_summary_structure_and_inr(self, sample_portfolio_data):
        """Verifies live portfolio summary contract and INR currency symbol."""
        summary = PortfolioAnalyticsService.get_live_portfolio_summary()
        assert summary['currency_symbol'] == '₹'
        assert summary['has_live_data'] is True
        assert 'kpis' in summary
        assert 'distributions' in summary
        assert 'time_series' in summary
        assert summary['kpis']['total_policies'] == 3
        assert summary['kpis']['gross_premium_written'] == Decimal('30000.00')


@pytest.mark.django_db
class TestPhase6AnalyticsRBACAndViews:

    def test_analytics_dashboard_customer_forbidden(self, client, test_users):
        """Customers must receive 403 Forbidden when attempting to access portfolio analytics."""
        client.force_login(test_users['customer'])
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code == 403

    def test_analytics_dashboard_underwriter_authorized(self, client, test_users):
        """Underwriters must receive 200 OK with live telemetry context."""
        client.force_login(test_users['underwriter'])
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200
        assert 'live_portfolio' in response.context
        assert 'Portfolio Analytics' in response.content.decode('utf-8')

    def test_analytics_dashboard_claims_handler_authorized(self, client, test_users):
        """Claims Handlers must receive 200 OK."""
        client.force_login(test_users['handler'])
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200

    def test_analytics_dashboard_admin_authorized(self, client, test_users):
        """Administrators must receive 200 OK."""
        client.force_login(test_users['admin'])
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200

    def test_analytics_dashboard_anonymous_demo_mode_allowed(self, client):
        """Anonymous visitors can view the educational demo dashboard for backward compatibility."""
        response = client.get(reverse('analytics:dashboard'))
        assert response.status_code == 200

    def test_live_portfolio_api_unauthenticated_rejected(self, client):
        """Unauthenticated requests to the live portfolio API must be rejected with 401."""
        response = client.get(reverse('analytics:api-portfolio'))
        assert response.status_code == 401

    def test_live_portfolio_api_customer_forbidden(self, client, test_users):
        """Customers calling the live portfolio API must receive 403 Forbidden."""
        client.force_login(test_users['customer'])
        response = client.get(reverse('analytics:api-portfolio'))
        assert response.status_code == 403

    def test_live_portfolio_api_staff_authorized(self, client, test_users, sample_portfolio_data):
        """Staff/Underwriters calling the live portfolio API receive full JSON telemetry."""
        client.force_login(test_users['underwriter'])
        response = client.get(reverse('analytics:api-portfolio'))
        assert response.status_code == 200
        data = response.json()
        assert data['currency_symbol'] == '₹'
        assert data['kpis']['total_policies'] == 3
        assert data['has_live_data'] is True
        assert 'distributions' in data
