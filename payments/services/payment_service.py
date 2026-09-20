import re
import uuid
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

from payments.models import SimulatedPayment, CardNetwork
from quotations.models import QuotationDraft
from policies.models import Policy
from policies.services.policy_service import PolicyService
from customers.models import CustomerProfile
from audit.services.audit_service import AuditService
from core.services import ServiceValidationError, NotificationService



class PaymentService:
    """
    Simulated educational payment gateway and checkout service:
    1. Card brand recognition via standard BIN prefix definitions.
    2. Modulo-10 Luhn checksum algorithm validation.
    3. Expiry and CVV security checks.
    4. Deterministic test card responses (Approved, Declined, Blocked).
    5. Automatic policy issuance and non-repudiation audit logging.
    """

    @classmethod
    def clean_card_number(cls, card_number: str) -> str:
        """Removes spaces, hyphens, and non-digit characters."""
        return re.sub(r'\D', '', str(card_number or ''))

    @classmethod
    def detect_card_network(cls, card_number: str) -> str:
        """Identifies card network from BIN prefix and length."""
        cleaned = cls.clean_card_number(card_number)
        if not cleaned:
            return CardNetwork.OTHER

        # Visa: Starts with 4, length 13, 16, or 19
        if cleaned.startswith('4'):
            return CardNetwork.VISA

        # Mastercard: Starts with 51-55 or 2221-2720, length 16
        if len(cleaned) >= 2:
            prefix2 = int(cleaned[:2])
            if 51 <= prefix2 <= 55:
                return CardNetwork.MASTERCARD
        if len(cleaned) >= 4:
            prefix4 = int(cleaned[:4])
            if 2221 <= prefix4 <= 2720:
                return CardNetwork.MASTERCARD

        # American Express: Starts with 34 or 37, length 15
        if cleaned.startswith('34') or cleaned.startswith('37'):
            return CardNetwork.AMEX

        # Discover: Starts with 6011, 65, or 644-649, length 16
        if cleaned.startswith('6011') or cleaned.startswith('65'):
            return CardNetwork.DISCOVER
        if len(cleaned) >= 3:
            prefix3 = int(cleaned[:3])
            if 644 <= prefix3 <= 649:
                return CardNetwork.DISCOVER

        return CardNetwork.OTHER

    @classmethod
    def validate_luhn(cls, card_number: str) -> bool:
        """
        Validates card number using the Luhn Algorithm (Mod 10).
        Doubles every second digit from right to left, subtracting 9 if > 9.
        Returns True if total sum modulo 10 equals 0.
        """
        cleaned = cls.clean_card_number(card_number)
        if not cleaned or len(cleaned) < 13 or len(cleaned) > 19:
            return False

        digits = [int(d) for d in cleaned]
        checksum = 0
        reverse_digits = digits[::-1]

        for i, digit in enumerate(reverse_digits):
            if i % 2 == 1:
                doubled = digit * 2
                checksum += (doubled - 9) if doubled > 9 else doubled
            else:
                checksum += digit

        return (checksum % 10) == 0

    @classmethod
    def validate_expiry(cls, expiry_str: str) -> bool:
        """
        Validates expiration date in MM/YY or MM/YYYY format.
        Must represent a future date relative to the current month.
        """
        cleaned = expiry_str.strip()
        match = re.match(r'^(0[1-9]|1[0-2])\/(\d{2}|\d{4})$', cleaned)
        if not match:
            return False

        month = int(match.group(1))
        year_str = match.group(2)

        if len(year_str) == 2:
            year = 2000 + int(year_str)
        else:
            year = int(year_str)

        today = date.today()
        # Card expires at the end of the specified month
        if year < today.year:
            return False
        if year == today.year and month < today.month:
            return False
        return True

    @classmethod
    def validate_cvv(cls, cvv_str: str, network: str) -> bool:
        """Validates security CVV/CVC code (3 digits standard, 4 digits for Amex)."""
        cleaned = re.sub(r'\D', '', str(cvv_str or ''))
        if network == CardNetwork.AMEX:
            return len(cleaned) == 4
        return len(cleaned) == 3

    @classmethod
    def mask_card_number(cls, card_number: str) -> str:
        """Masks card number preserving only the final 4 digits."""
        cleaned = cls.clean_card_number(card_number)
        if len(cleaned) < 4:
            return "**** **** **** ****"
        last4 = cleaned[-4:]
        return f"**** **** **** {last4}"

    @classmethod
    def process_simulated_payment(
        cls,
        amount: Decimal,
        card_number: str,
        expiry: str,
        cvv: str,
        quotation: Optional[QuotationDraft] = None,
        policy: Optional[Policy] = None,
        customer: Optional[CustomerProfile] = None,
        user=None,
    ) -> SimulatedPayment:
        """
        Processes simulated payment transaction:
        1. Validates card number format and Luhn checksum.
        2. Validates expiry date and CVV length.
        3. Simulates gateway approval / decline based on test card rules.
        4. Issues Policy if payment succeeds for a quotation draft.
        5. Writes audit log.
        """
        cleaned_num = cls.clean_card_number(card_number)
        network = cls.detect_card_network(cleaned_num)

        # 1. Luhn Checksum Validation
        if not cls.validate_luhn(cleaned_num):
            raise ServiceValidationError("Invalid card number. Failed Luhn checksum validation.")

        # 2. Expiry Validation
        if not cls.validate_expiry(expiry):
            raise ServiceValidationError("Invalid or expired card expiration date (format MM/YY or MM/YYYY).")

        # 3. CVV Validation
        if not cls.validate_cvv(cvv, network):
            expected_digits = "4 digits for American Express" if network == CardNetwork.AMEX else "3 digits"
            raise ServiceValidationError(f"Invalid CVV code. Expected {expected_digits}.")

        # 4. Gateway Simulation Logic
        last4 = cleaned_num[-4:]
        if last4 == '0002':
            is_successful = False
            response_code = 'DECLINED_INSUFFICIENT_FUNDS'
            response_msg = 'Transaction declined: Insufficient funds in simulated account.'
        elif last4 == '0003':
            is_successful = False
            response_code = 'BLOCKED_FRAUD_RISK'
            response_msg = 'Transaction blocked: High fraud risk simulation threshold exceeded.'
        else:
            is_successful = True
            response_code = 'APPROVED'
            response_msg = 'Transaction authorized successfully.'

        masked_num = cls.mask_card_number(cleaned_num)
        txn_id = f"SIM-TXN-{timezone.now().year}-{uuid.uuid4().hex[:10].upper()}"

        with transaction.atomic():
            issued_policy = policy

            # If payment is successful and paid against a quotation draft, auto-issue the policy!
            if is_successful and quotation and not issued_policy:
                issued_policy = PolicyService.issue_policy_from_quotation(
                    quotation=quotation,
                    underwriter=None  # Direct online automated customer purchase
                )

            payment = SimulatedPayment.objects.create(
                quotation=quotation,
                policy=issued_policy,
                amount=amount,
                currency='INR',
                card_network=network,
                masked_card_number=masked_num,
                simulated_transaction_id=txn_id,
                is_successful=is_successful,
                simulated_gateway_response={
                    'code': response_code,
                    'message': response_msg,
                    'processed_at': timezone.now().isoformat(),
                    'network': network,
                    'test_mode': True,
                }
            )

            # Compliance audit log
            AuditService.log(
                action='PAYMENT_PROCESSED',
                target_entity='SimulatedPayment',
                target_id=str(payment.id),
                actor=user,
                is_success=is_successful,
                details={
                    'transaction_id': txn_id,
                    'amount': str(amount),
                    'network': network,
                    'is_successful': is_successful,
                    'policy_number': issued_policy.policy_number if issued_policy else None,
                }
            )

            if user and getattr(user, 'is_authenticated', False):
                if is_successful:
                    NotificationService.notify(
                        recipient=user,
                        title="Payment Authorized",
                        message=f"Payment of ₹{amount:,.2f} authorized successfully. Policy {issued_policy.policy_number if issued_policy else ''} is active. Transaction: {txn_id}.",
                        notification_type='GENERAL',
                        action_url=f"/policies/{issued_policy.id}/" if issued_policy else "/customer/policies/",
                    )
                else:
                    NotificationService.notify(
                        recipient=user,
                        title="Payment Declined",
                        message=f"Payment of ₹{amount:,.2f} declined: {response_msg}. Transaction: {txn_id}.",
                        notification_type='SECURITY_ALERT',
                        action_url="/quotations/",
                    )

        if not is_successful:
            raise ServiceValidationError(response_msg)

        return payment

