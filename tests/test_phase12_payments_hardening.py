import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.customers.models import CustomerProfile
from apps.vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from apps.quotations.models import CoveragePlan, CoveragePlanCode, QuotationDraft
from apps.policies.models import Policy, PolicyStatus
from apps.payments.models import SimulatedPayment, CardNetwork
from apps.payments.services.payment_service import PaymentService
from apps.audit.models import AuditLog
from core.services import ServiceValidationError


@pytest.mark.django_db
class TestPhase12PaymentsAndHardening:
    """
    Test suite verifying Phase 12 simulated payments, Luhn validation,
    card brand detection, automated policy issuance, and security hardening.
    """

    @pytest.fixture
    def customer_user(self):
        user = User.objects.create_user(
            username='cust_pay',
            email='cust_pay@nexisure.test',
            first_name='Catherine',
            last_name='Fox',
            role=UserRole.CUSTOMER,
        )
        CustomerProfile.objects.create(
            user=user,
            customer_code='CUST-PAY-01',
            date_of_birth=date(1992, 7, 20),
            address_line='500 Financial Center Blvd',
            city='Boston',
            postal_code='02110',
        )
        return user

    @pytest.fixture
    def sample_plan(self):
        plan, _ = CoveragePlan.objects.get_or_create(
            plan_code=CoveragePlanCode.COMPREHENSIVE,
            defaults={
                'name': 'Comprehensive Plus',
                'description': 'Comprehensive plan with full collision coverage',
                'base_rate_percentage': Decimal('3.50'),
            }
        )
        return plan

    @pytest.fixture
    def sample_vehicle(self, customer_user):
        return Vehicle.objects.create(
            customer=customer_user.customer_profile,
            registration_number='WA02AP9999',
            make='Tesla',
            model='Model 3',
            manufacture_year=2023,
            vehicle_type=VehicleType.SEDAN,
            fuel_type=FuelType.ELECTRIC,
            usage_type=UsageType.PERSONAL,
            vehicle_value=Decimal('35000.00'),
            chassis_number='CHASSIS-TESLA-9999',
        )

    @pytest.fixture
    def sample_quotation(self, customer_user, sample_plan, sample_vehicle):
        draft = QuotationDraft.objects.create(
            quotation_number='QUOTE-PAY-001',
            customer=customer_user.customer_profile,
            coverage_plan=sample_plan,
            vehicle=sample_vehicle,
            vehicle_value=sample_vehicle.vehicle_value,
            duration_years=1,
            calculated_premium=Decimal('1250.00'),
            deductible_amount=Decimal('500.00'),
            valid_until=timezone.now() + timedelta(days=14),
        )
        return draft

    def test_luhn_algorithm_validation(self):
        # Valid test card numbers
        assert PaymentService.validate_luhn('4532000000080001') is True
        assert PaymentService.validate_luhn('5425233430109903') is True
        assert PaymentService.validate_luhn('378282246310005') is True

        # Invalid checksum cards
        assert PaymentService.validate_luhn('4532000000080009') is False
        assert PaymentService.validate_luhn('1234567890123456') is False
        assert PaymentService.validate_luhn('not_a_number') is False

    def test_card_network_detection(self):
        assert PaymentService.detect_card_network('4532000000080001') == CardNetwork.VISA
        assert PaymentService.detect_card_network('5425233430109903') == CardNetwork.MASTERCARD
        assert PaymentService.detect_card_network('378282246310005') == CardNetwork.AMEX
        assert PaymentService.detect_card_network('6011111111111117') == CardNetwork.DISCOVER
        assert PaymentService.detect_card_network('9999999999999999') == CardNetwork.OTHER

    def test_expiry_and_cvv_validation(self):
        # Future expiry
        assert PaymentService.validate_expiry('12/28') is True
        assert PaymentService.validate_expiry('01/2030') is True

        # Past expiry
        assert PaymentService.validate_expiry('01/20') is False
        assert PaymentService.validate_expiry('12/19') is False
        assert PaymentService.validate_expiry('invalid_date') is False

        # CVV
        assert PaymentService.validate_cvv('123', CardNetwork.VISA) is True
        assert PaymentService.validate_cvv('12', CardNetwork.VISA) is False
        assert PaymentService.validate_cvv('1234', CardNetwork.AMEX) is True
        assert PaymentService.validate_cvv('123', CardNetwork.AMEX) is False

    def test_payment_simulation_decline_and_fraud_block(self, sample_quotation):
        # Insufficient funds card ending in 0002
        with pytest.raises(ServiceValidationError) as exc1:
            PaymentService.process_simulated_payment(
                amount=sample_quotation.calculated_premium,
                card_number='4532000000070002',
                expiry='12/28',
                cvv='123',
                quotation=sample_quotation,
            )
        assert 'Insufficient funds' in str(exc1.value)

        # High fraud risk card ending in 0003
        with pytest.raises(ServiceValidationError) as exc2:
            PaymentService.process_simulated_payment(
                amount=sample_quotation.calculated_premium,
                card_number='4532000000060003',
                expiry='12/28',
                cvv='123',
                quotation=sample_quotation,
            )
        assert 'fraud risk' in str(exc2.value).lower()

    def test_successful_payment_auto_issues_policy(self, sample_quotation, customer_user):
        payment = PaymentService.process_simulated_payment(
            amount=sample_quotation.calculated_premium,
            card_number='4532000000080001',
            expiry='12/28',
            cvv='123',
            quotation=sample_quotation,
            user=customer_user,
        )

        assert payment.is_successful is True
        assert payment.policy is not None
        assert payment.policy.status == PolicyStatus.ACTIVE
        assert payment.policy.customer == sample_quotation.customer
        assert payment.masked_card_number == '**** **** **** 0001'

        # Verify audit log
        audit = AuditLog.objects.filter(
            action='PAYMENT_PROCESSED',
            target_entity='SimulatedPayment',
            target_id=str(payment.id),
        ).first()
        assert audit is not None
        assert audit.is_success is True

    def test_checkout_and_success_views(self, client, sample_quotation):
        # 1. GET Checkout
        url_checkout = reverse('payments:checkout') + f"?quotation_id={sample_quotation.id}"
        resp_get = client.get(url_checkout)
        assert resp_get.status_code == 200
        content_get = resp_get.content.decode('utf-8')
        assert 'Simulated Premium Checkout' in content_get
        assert '1250' in content_get

        # 2. POST Checkout (Authorize payment)
        post_data = {
            'quotation_id': str(sample_quotation.id),
            'amount': str(sample_quotation.calculated_premium),
            'card_number': '4532000000080001',
            'expiry': '12/28',
            'cvv': '123',
        }
        resp_post = client.post(reverse('payments:checkout'), data=post_data)
        assert resp_post.status_code == 302
        assert reverse('payments:success') in resp_post.url

        # 3. GET Success View
        resp_success = client.get(resp_post.url)
        assert resp_success.status_code == 200
        assert 'Simulated Transaction Approved' in resp_success.content.decode('utf-8')
