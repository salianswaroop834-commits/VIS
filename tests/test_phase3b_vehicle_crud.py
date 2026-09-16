import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, UserRole
from customers.models import CustomerProfile
from vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from vehicles.services.vehicle_service import VehicleService
from quotations.models import CoveragePlan
from policies.models import Policy, PolicyStatus
from audit.models import AuditLog, AuditAction
from core.services import ServiceValidationError


@pytest.mark.django_db
class TestPhase3BVehicleCrud:
    """
    Test suite for Phase 3B: Complete Vehicle Asset CRUD, Ownership Isolation,
    Active Policy Financial Lock, and Non-destructive Deactivation.
    """

    @pytest.fixture(autouse=True)
    def setup_entities(self):
        # Customer A
        self.user_a = User.objects.create_user(
            username='alice_vehicle',
            email='alice.owner@example.com',
            role=UserRole.CUSTOMER,
            first_name='Alice',
            last_name='Owner',
            password='password123',
        )
        self.customer_a = CustomerProfile.objects.create(
            user=self.user_a,
            customer_code='CUST-ALICE-101',
        )

        # Customer B
        self.user_b = User.objects.create_user(
            username='bob_vehicle',
            email='bob.intruder@example.com',
            role=UserRole.CUSTOMER,
            first_name='Bob',
            last_name='Intruder',
            password='password123',
        )

        self.customer_b = CustomerProfile.objects.create(
            user=self.user_b,
            customer_code='CUST-BOB-202',
        )

        # Vehicle A owned by Customer A
        self.vehicle_a = VehicleService.create_vehicle(
            customer=self.customer_a,
            data={
                'registration_number': 'MH01AB1234',
                'chassis_number': '1HGCR2F83HA001234',
                'make': 'Honda',
                'model': 'City ZX',
                'manufacture_year': 2022,
                'vehicle_type': VehicleType.SEDAN,
                'fuel_type': FuelType.PETROL,
                'usage_type': UsageType.PERSONAL,
                'vehicle_value': '1200000.00',
            }
        )

        # Vehicle B owned by Customer B
        self.vehicle_b = VehicleService.create_vehicle(
            customer=self.customer_b,
            data={
                'registration_number': 'KA05CD5678',
                'chassis_number': '2T3RFREV9KW005678',
                'make': 'Toyota',
                'model': 'Fortuner',
                'manufacture_year': 2023,
                'vehicle_type': VehicleType.SUV,
                'fuel_type': FuelType.DIESEL,
                'usage_type': UsageType.PERSONAL,
                'vehicle_value': '3500000.00',
            }
        )

        # Active Coverage Plan
        self.plan = CoveragePlan.objects.create(
            name='Comprehensive Protection',
            plan_code='COMPREHENSIVE',
            base_rate_percentage=Decimal('2.50'),
            standard_deductible=Decimal('2000.00'),
            is_active=True,
        )

    def test_vehicle_detail_loads_successfully_for_owner(self, client):
        client.force_login(self.user_a)
        resp = client.get(reverse('vehicles:detail', kwargs={'pk': self.vehicle_a.pk}))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'Honda' in content
        assert 'City ZX' in content
        assert 'MH01AB1234' in content
        assert '₹' in content
        assert '1,200,000.00' in content or '1200000' in content
        assert 'Active Asset' in content

    def test_customer_cannot_access_another_customers_vehicle_detail(self, client):
        # Customer B attempts to view Customer A's vehicle
        client.force_login(self.user_b)
        resp = client.get(reverse('vehicles:detail', kwargs={'pk': self.vehicle_a.pk}))
        assert resp.status_code == 403

    def test_vehicle_edit_get_works(self, client):
        client.force_login(self.user_a)
        resp = client.get(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'Honda' in content
        assert 'MH01AB1234' in content
        assert '₹' in content

    def test_valid_vehicle_update_without_active_policy(self, client):
        client.force_login(self.user_a)
        update_data = {
            'make': 'Honda',
            'model': 'City e:HEV',
            'registration_number': 'MH01AB9999',
            'chassis_number': '1HGCR2F83HA009999',
            'manufacture_year': '2023',
            'vehicle_type': VehicleType.SEDAN,
            'fuel_type': FuelType.HYBRID,
            'usage_type': UsageType.PERSONAL,
            'engine_number': 'ENG998877',
            'vehicle_value': '1450000.00',
        }
        resp = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data=update_data)
        assert resp.status_code == 302
        self.vehicle_a.refresh_from_db()
        assert self.vehicle_a.model == 'City e:HEV'
        assert self.vehicle_a.registration_number == 'MH01AB9999'
        assert self.vehicle_a.fuel_type == FuelType.HYBRID
        assert self.vehicle_a.vehicle_value == Decimal('1450000.00')

        # Audit log verification
        audit = AuditLog.objects.filter(
            target_entity='Vehicle',
            target_id=str(self.vehicle_a.pk),
            action=AuditAction.VEHICLE_UPDATED,
        ).first()
        assert audit is not None
        assert audit.actor == self.user_a

    def test_input_normalization_on_update(self, client):
        client.force_login(self.user_a)
        resp = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data={
            'make': '  Honda  ',
            'model': '  City  ',
            'registration_number': 'mh-01-cd-4444',
            'chassis_number': '1h gcr2f8 3ha004444',
            'manufacture_year': '2022',
            'vehicle_type': VehicleType.SEDAN,
            'fuel_type': FuelType.PETROL,
            'usage_type': UsageType.PERSONAL,
            'vehicle_value': '1200000.00',
        })
        assert resp.status_code == 302
        self.vehicle_a.refresh_from_db()
        assert self.vehicle_a.registration_number == 'MH01CD4444'
        assert self.vehicle_a.chassis_number == '1HGCR2F83HA004444'
        assert self.vehicle_a.make == 'Honda'

    def test_active_policy_financial_lock_blocks_plate_and_idv_mutation(self, client):
        # Create an ACTIVE policy on vehicle_a
        Policy.objects.create(
            policy_number='POL-2026-TEST001',
            customer=self.customer_a,
            vehicle=self.vehicle_a,
            coverage_plan=self.plan,
            premium_amount=Decimal('30000.00'),
            deductible_amount=Decimal('2000.00'),
            duration_years=1,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=365),
            status=PolicyStatus.ACTIVE,
        )

        # Service-layer direct test
        with pytest.raises(ServiceValidationError, match="Cannot modify registration plate of a vehicle with an active policy"):
            VehicleService.update_vehicle(
                vehicle=self.vehicle_a,
                customer=self.customer_a,
                data={'registration_number': 'DL01ZZ0001'},
            )

        with pytest.raises(ServiceValidationError, match="Vehicle valuation \\(IDV\\) is locked by an active policy"):
            VehicleService.update_vehicle(
                vehicle=self.vehicle_a,
                customer=self.customer_a,
                data={'vehicle_value': '1800000.00'},
            )

        # View-layer test: Edit page displays active-policy warning
        client.force_login(self.user_a)
        resp_get = client.get(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}))
        assert resp_get.status_code == 200
        assert 'Active Policy Financial Lock' in resp_get.content.decode('utf-8')

        # Non-financial update under active policy SUCCEEDS
        resp_post = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data={
            'fuel_type': FuelType.CNG,
            'usage_type': UsageType.COMMERCIAL,
            'engine_number': 'ENG-CNG-999',
        })
        assert resp_post.status_code == 302
        self.vehicle_a.refresh_from_db()
        assert self.vehicle_a.fuel_type == FuelType.CNG
        assert self.vehicle_a.usage_type == UsageType.COMMERCIAL
        assert self.vehicle_a.registration_number == 'MH01AB1234'  # Locked

    def test_invalid_manufacture_year_is_rejected(self, client):
        client.force_login(self.user_a)
        resp = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data={
            'make': 'Honda',
            'model': 'City',
            'registration_number': 'MH01AB1234',
            'chassis_number': '1HGCR2F83HA001234',
            'manufacture_year': '1970',  # Too old (< 1980)
            'vehicle_value': '1200000.00',
        })
        assert resp.status_code == 200
        assert 'Manufacture year must be between 1980 and' in resp.content.decode('utf-8')

    def test_duplicate_registration_plate_rejected(self, client):
        client.force_login(self.user_a)
        # Attempt to change vehicle A plate to vehicle B plate (KA05CD5678)
        resp = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data={
            'make': 'Honda',
            'model': 'City',
            'registration_number': 'KA05CD5678',
            'chassis_number': '1HGCR2F83HA001234',
            'manufacture_year': '2022',
            'vehicle_value': '1200000.00',
        })
        assert resp.status_code == 200
        assert 'already exists in the system' in resp.content.decode('utf-8')

    def test_vehicle_deactivation_succeeds_without_active_policy(self, client):
        client.force_login(self.user_a)
        resp = client.post(reverse('vehicles:deactivate', kwargs={'pk': self.vehicle_a.pk}))
        assert resp.status_code == 302
        self.vehicle_a.refresh_from_db()
        assert self.vehicle_a.is_active is False

        # Verify audit log
        audit = AuditLog.objects.filter(
            target_entity='Vehicle',
            target_id=str(self.vehicle_a.pk),
            action=AuditAction.VEHICLE_DEACTIVATED,
        ).first()
        assert audit is not None
        assert audit.actor == self.user_a

    def test_vehicle_deactivation_blocked_when_active_policy_exists(self, client):
        # Create active policy on vehicle A
        Policy.objects.create(
            policy_number='POL-2026-TEST002',
            customer=self.customer_a,
            vehicle=self.vehicle_a,
            coverage_plan=self.plan,
            premium_amount=Decimal('30000.00'),
            deductible_amount=Decimal('2000.00'),
            duration_years=1,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=365),
            status=PolicyStatus.ACTIVE,
        )

        client.force_login(self.user_a)
        resp = client.post(reverse('vehicles:deactivate', kwargs={'pk': self.vehicle_a.pk}))
        assert resp.status_code == 302
        self.vehicle_a.refresh_from_db()
        assert self.vehicle_a.is_active is True  # Remained active!

    def test_unauthorized_user_cannot_edit_or_deactivate_another_vehicle(self, client):
        client.force_login(self.user_b)

        # GET Edit
        resp_get = client.get(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}))
        assert resp_get.status_code == 403

        # POST Edit
        resp_post = client.post(reverse('vehicles:edit', kwargs={'pk': self.vehicle_a.pk}), data={
            'make': 'Malicious',
        })
        assert resp_post.status_code == 403

        # POST Deactivate
        resp_deact = client.post(reverse('vehicles:deactivate', kwargs={'pk': self.vehicle_a.pk}))
        assert resp_deact.status_code == 403

    def test_currency_consistency_inr_presentation(self, client):
        client.force_login(self.user_a)

        # Vehicle Detail
        resp_veh = client.get(reverse('vehicles:detail', kwargs={'pk': self.vehicle_a.pk}))
        assert resp_veh.status_code == 200
        content_veh = resp_veh.content.decode('utf-8')
        assert '₹' in content_veh
        assert '$1,200,000' not in content_veh

        # Customer Vehicles List
        resp_list = client.get(reverse('customers:vehicles'))
        assert resp_list.status_code == 200
        content_list = resp_list.content.decode('utf-8')
        assert '₹' in content_list
        assert '$1,200,000' not in content_list

        # Policy Detail
        policy = Policy.objects.create(
            policy_number='POL-2026-INR001',
            customer=self.customer_a,
            vehicle=self.vehicle_a,
            coverage_plan=self.plan,
            premium_amount=Decimal('25000.00'),
            deductible_amount=Decimal('1500.00'),
            duration_years=1,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=365),
            status=PolicyStatus.ACTIVE,
        )
        resp_pol = client.get(reverse('policies:detail', kwargs={'pk': policy.pk}))
        assert resp_pol.status_code == 200
        content_pol = resp_pol.content.decode('utf-8')
        assert '₹' in content_pol
        assert '$25,000.00' not in content_pol
        assert '$1,500.00' not in content_pol

        # Checkout
        resp_chk = client.get(reverse('payments:checkout'))
        assert resp_chk.status_code == 200
        content_chk = resp_chk.content.decode('utf-8')
        assert '₹' in content_chk
