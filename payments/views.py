from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.urls import reverse

from quotations.models import QuotationDraft
from policies.models import Policy
from .models import SimulatedPayment
from .services.payment_service import PaymentService
from core.services import ServiceValidationError


class CheckoutView(View):
    """
    Simulated checkout interface.
    Performs Luhn checksum validation, card network detection, and mock payment settlement.
    """
    template_name = 'payments/checkout.html'

    def get(self, request):
        quotation_id = request.GET.get('quotation_id')
        policy_id = request.GET.get('policy_id')

        quotation = None
        policy = None
        amount = Decimal('712.50')
        item_title = "Vehicle Insurance Annual Premium"

        if quotation_id:
            try:
                quotation = QuotationDraft.objects.select_related('vehicle', 'coverage_plan').get(pk=quotation_id)
                amount = quotation.calculated_premium
                item_title = f"{quotation.coverage_plan.name} Coverage ({quotation.duration_years} Year{'s' if quotation.duration_years > 1 else ''})"
            except QuotationDraft.DoesNotExist:
                pass
        elif policy_id:
            try:
                policy = Policy.objects.select_related('vehicle', 'coverage_plan').get(pk=policy_id)
                amount = policy.premium_amount
                item_title = f"Policy Renewal: {policy.policy_number} ({policy.coverage_plan.name})"
            except Policy.DoesNotExist:
                pass

        return render(request, self.template_name, {
            'quotation': quotation,
            'policy': policy,
            'amount': amount,
            'item_title': item_title,
        })

    def post(self, request):
        quotation_id = request.POST.get('quotation_id')
        policy_id = request.POST.get('policy_id')
        card_number = request.POST.get('card_number', '')
        expiry = request.POST.get('expiry', '')
        cvv = request.POST.get('cvv', '')
        amount_str = request.POST.get('amount', '712.50')

        quotation = None
        policy = None
        if quotation_id:
            quotation = QuotationDraft.objects.filter(pk=quotation_id).first()
        if policy_id:
            policy = Policy.objects.filter(pk=policy_id).first()

        try:
            amount = Decimal(amount_str)
            payment = PaymentService.process_simulated_payment(
                amount=amount,
                card_number=card_number,
                expiry=expiry,
                cvv=cvv,
                quotation=quotation,
                policy=policy,
                user=request.user if request.user.is_authenticated else None,
            )
            return redirect(f"{reverse('payments:success')}?txn_id={payment.simulated_transaction_id}")
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {
                'quotation': quotation,
                'policy': policy,
                'amount': amount_str,
                'card_number': card_number,
                'expiry': expiry,
                'item_title': "Vehicle Insurance Premium Checkout",
            })


class PaymentSuccessView(View):
    """
    Renders receipt of the authorized simulated payment transaction.
    """
    template_name = 'payments/success.html'

    def get(self, request):
        txn_id = request.GET.get('txn_id')
        payment = None
        if txn_id:
            payment = SimulatedPayment.objects.filter(simulated_transaction_id=txn_id).select_related('policy', 'quotation').first()

        return render(request, self.template_name, {
            'payment': payment,
            'txn_id': txn_id or 'SIM-TXN-2026-DEMO',
        })
