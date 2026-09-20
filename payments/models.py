from django.db import models
from core.models import AuditableModel
from quotations.models import QuotationDraft
from policies.models import Policy


class CardNetwork(models.TextChoices):
    VISA = 'VISA', 'Visa'
    MASTERCARD = 'MASTERCARD', 'Mastercard'
    AMEX = 'AMEX', 'American Express'
    DISCOVER = 'DISCOVER', 'Discover'
    OTHER = 'OTHER', 'Other / Unknown Network'


class PaymentMethod(models.TextChoices):
    CREDIT_CARD = 'CREDIT_CARD', 'Credit Card'
    DEBIT_CARD = 'DEBIT_CARD', 'Debit Card'
    NET_BANKING = 'NET_BANKING', 'Net Banking (Simulated)'
    UPI = 'UPI', 'UPI (Simulated)'


class SimulatedPayment(AuditableModel):
    """
    Simulated educational payment transaction.
    Demonstrates Luhn checksum validation, card network recognition,
    and mock payment status without storing real financial credentials.
    """
    quotation = models.ForeignKey(
        QuotationDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CREDIT_CARD,
    )
    card_network = models.CharField(
        max_length=20,
        choices=CardNetwork.choices,
        default=CardNetwork.VISA,
    )
    masked_card_number = models.CharField(
        max_length=25,
        help_text='Masked card representation e.g., **** **** **** 4242',
    )
    simulated_transaction_id = models.CharField(max_length=50, unique=True, db_index=True)
    is_successful = models.BooleanField(default=True)
    simulated_gateway_response = models.JSONField(default=dict)
    disclaimer = models.TextField(
        default='Simulated educational payment demonstration. No real funds or sensitive card data are processed.'
    )

    class Meta:
        verbose_name = 'Simulated Payment'
        verbose_name_plural = 'Simulated Payments'
        ordering = ['-created_at']

    def __str__(self):
        status = 'SUCCESS' if self.is_successful else 'FAILED'
        return f"{self.simulated_transaction_id} - ₹{self.amount} ({status})"
