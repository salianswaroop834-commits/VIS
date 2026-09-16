from decimal import Decimal
import uuid
from typing import Optional
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from quotations.models import CoveragePlan, QuotationDraft, CoveragePlanCode, CoverageFeature
from quotations.services.quotation_service import QuotationService
from quotations.selectors import (
    get_active_coverage_plans,
    get_coverage_plan_by_code,
    get_customer_quotations,
    get_quotation_by_number,
    get_quotation_by_id,
)
from vehicles.selectors import get_customer_vehicles
from policies.services.policy_service import PolicyService
from payments.services.payment_service import PaymentService
from core.services import ServiceValidationError
from core.permissions import CustomerRequiredMixin


class CustomerQuotationListView(LoginRequiredMixin, ListView):
    """
    Displays the customer's personal vehicle quotation portfolio.
    Guarantees strict customer data isolation.
    """
    template_name = 'quotations/quotation_list.html'
    context_object_name = 'quotations'

    def get_queryset(self):
        user = self.request.user
        if user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if not customer:
                return QuotationDraft.objects.none()
            return get_customer_quotations(customer)
        elif user.is_underwriter:
            staff = getattr(user, 'staff_profile', None)
            return QuotationDraft.objects.filter(underwriter=staff).select_related(
                'customer__user', 'vehicle', 'coverage_plan'
            ).order_by('-created_at')
        elif user.is_administrator:
            return QuotationDraft.objects.all().select_related(
                'customer__user', 'vehicle', 'coverage_plan', 'underwriter'
            ).order_by('-created_at')
        return QuotationDraft.objects.none()


class CoverageComparisonView(ListView):
    """
    Customer-accessible page displaying active CoveragePlans and itemized features.
    Distinguishes standard features from optional add-on riders.
    Formatted in Indian Rupees (₹).
    """
    model = CoveragePlan
    template_name = 'quotations/compare_plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return get_active_coverage_plans()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['currency_symbol'] = '₹'
        return context


class QuotationCreateView(View):
    """
    Customer premium estimator and quotation draft generator.
    Enforces server-side customer ownership of registered vehicles.
    """
    template_name = 'quotations/estimator.html'

    def get(self, request):
        plans = get_active_coverage_plans()
        vehicles = []

        if request.user.is_authenticated and request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if customer:
                vehicles = get_customer_vehicles(customer)

        selected_vehicle_id = request.GET.get('vehicle_id', '')
        selected_plan = request.GET.get('plan', CoveragePlanCode.COMPREHENSIVE)
        prefill_value = request.GET.get('vehicle_value', '500000')

        return render(request, self.template_name, {
            'plans': plans,
            'vehicles': vehicles,
            'selected_vehicle_id': selected_vehicle_id,
            'selected_plan': selected_plan,
            'prefill_value': prefill_value,
            'currency_symbol': '₹',
        })

    def post(self, request):
        if not request.user.is_authenticated:
            messages.info(request, "Please sign in or register to generate an official vehicle insurance quotation.")
            return redirect(f"/auth/login/?next={request.path}")

        customer = getattr(request.user, 'customer_profile', None)
        if not customer and request.user.is_customer:
            messages.error(request, "Please complete your customer profile before requesting quotations.")
            return redirect('customers:profile')

        try:
            val_str = request.POST.get('vehicle_value', '500000').strip()
            vehicle_value = Decimal(str(val_str))
            plan_code = request.POST.get('coverage_plan', CoveragePlanCode.COMPREHENSIVE)
            duration_years = int(request.POST.get('duration_years', 1))

            # Selected optional riders / features
            selected_feature_ids = request.POST.getlist('selected_features')

            # Validate vehicle selection and server-side customer ownership
            v_id = request.POST.get('vehicle_id', '').strip()
            vehicle = None
            if v_id:
                if not customer:
                    raise ServiceValidationError("Unauthorized: Only customers with registered profiles can associate vehicles.")
                vehicle = customer.vehicles.filter(id=v_id, is_active=True).first()
                if not vehicle:
                    raise ServiceValidationError("Security Error: The selected vehicle does not belong to your account.")
                # Override vehicle_value with authenticated vehicle's recorded IDV
                vehicle_value = vehicle.vehicle_value

            draft = QuotationService.create_quotation_draft(
                vehicle_value=vehicle_value,
                plan_code=plan_code,
                duration_years=duration_years,
                customer=customer,
                vehicle=vehicle,
                selected_feature_ids=selected_feature_ids,
                actor=request.user,
            )

            messages.success(request, f"Quotation '{draft.quotation_number}' generated successfully!")
            return redirect('quotations:detail', pk=draft.pk)

        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('quotations:estimator')
        except Exception as e:
            messages.error(request, f"Failed to generate quote: {str(e)}")
            return redirect('quotations:estimator')


class QuotationDetailView(View):
    """
    Renders official quotation draft details, premium breakdown,
    itemized features, and status progression in Indian Rupees (₹).
    Enforces object-level customer ownership isolation.
    """
    template_name = 'quotations/quotation_detail.html'

    def get_quotation(self, kwargs) -> QuotationDraft:
        pk = kwargs.get('pk')
        quotation_number = kwargs.get('quotation_number')
        quotation = None

        if pk:
            quotation = get_quotation_by_id(pk)
        elif quotation_number:
            quotation = get_quotation_by_number(quotation_number)

        if not quotation:
            raise PermissionDenied("Quotation record not found.")

        # Security: Customer isolation check
        user = self.request.user
        if user.is_authenticated and user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if quotation.customer and quotation.customer != customer:
                raise PermissionDenied("Access Denied: You cannot access another customer's quotation.")

        return quotation

    def get(self, request, *args, **kwargs):
        quotation = self.get_quotation(kwargs)

        # Check temporal expiry
        if quotation.status == QuotationDraft.QuotationStatus.DRAFT and quotation.valid_until < timezone.now():
            quotation.status = QuotationDraft.QuotationStatus.EXPIRED
            quotation.save(update_fields=['status', 'updated_at'])

        # Group plan features into standard and optional riders
        plan_features = quotation.coverage_plan.features.filter(is_active=True)
        standard_features = [f for f in plan_features if f.is_standard]
        optional_riders = [f for f in plan_features if not f.is_standard]
        selected_rider_ids = set(str(f.id) for f in quotation.selected_features.all())

        return render(request, self.template_name, {
            'quotation': quotation,
            'standard_features': standard_features,
            'optional_riders': optional_riders,
            'selected_rider_ids': selected_rider_ids,
            'currency_symbol': '₹',
        })


class QuotationAcceptView(View):
    """
    Customer quotation acceptance workflow.
    Transitions: DRAFT -> ACCEPTED
    Enforces customer ownership and valid non-expired state.
    """
    def post(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        quotation_number = kwargs.get('quotation_number')

        if pk:
            quotation = get_object_or_404(QuotationDraft, pk=pk)
        else:
            quotation = get_object_or_404(QuotationDraft, quotation_number=quotation_number.strip().upper())

        if not request.user.is_authenticated:
            messages.error(request, "Please sign in to accept your quotation.")
            return redirect(f"/auth/login/?next={request.path}")

        try:
            QuotationService.accept_quotation(quotation=quotation, actor=request.user)
            messages.success(
                request,
                f"Quotation '{quotation.quotation_number}' accepted successfully! Proceed to checkout or policy issuance."
            )
            return redirect('quotations:detail', pk=quotation.pk)

        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('quotations:detail', pk=quotation.pk)


class QuotationConvertView(View):
    """
    Converts an ACCEPTED quotation into an active vehicle insurance Policy.
    Supports simulated checkout demonstration or direct issuance.
    Transitions: ACCEPTED -> CONVERTED
    """
    template_name = 'quotations/convert_policy.html'

    def get_quotation(self, kwargs) -> QuotationDraft:
        pk = kwargs.get('pk')
        quotation_number = kwargs.get('quotation_number')
        if pk:
            return get_object_or_404(QuotationDraft, pk=pk)
        return get_object_or_404(QuotationDraft, quotation_number=quotation_number.strip().upper())

    def get(self, request, *args, **kwargs):
        quotation = self.get_quotation(kwargs)

        # Verification check
        if quotation.status == QuotationDraft.QuotationStatus.CONVERTED:
            messages.info(request, "This quotation has already been converted into an active policy.")
            policy = quotation.policies.first() if hasattr(quotation, 'policies') else None
            if policy:
                return redirect('policies:detail', pk=policy.pk)
            return redirect('quotations:detail', pk=quotation.pk)

        if quotation.status == QuotationDraft.QuotationStatus.EXPIRED:
            messages.error(request, "This quotation has expired. Please calculate a new quote.")
            return redirect('quotations:detail', pk=quotation.pk)

        return render(request, self.template_name, {
            'quotation': quotation,
            'currency_symbol': '₹',
        })

    def post(self, request, *args, **kwargs):
        quotation = self.get_quotation(kwargs)

        if not request.user.is_authenticated:
            messages.error(request, "Authentication required to issue policy.")
            return redirect('accounts:login')

        customer = getattr(request.user, 'customer_profile', None)
        if quotation.customer and quotation.customer != customer and not request.user.is_administrator:
            raise PermissionDenied("Unauthorized: You cannot convert another customer's quotation.")

        # Ensure quotation is linked to customer and vehicle before conversion
        if not quotation.customer and customer:
            quotation.customer = customer
            quotation.save(update_fields=['customer'])

        if not quotation.vehicle and customer:
            vehicle = customer.vehicles.filter(is_active=True).first()
            if vehicle:
                quotation.vehicle = vehicle
                quotation.save(update_fields=['vehicle'])
            else:
                messages.warning(request, "Please register your vehicle to complete policy conversion.")
                return redirect('vehicles:create')

        # Check payment simulation
        card_number = request.POST.get('card_number')
        expiry = request.POST.get('expiry')
        cvv = request.POST.get('cvv')

        try:
            if card_number and expiry and cvv:
                # Process via SimulatedPayment service
                payment = PaymentService.process_simulated_payment(
                    amount=quotation.calculated_premium,
                    card_number=card_number,
                    expiry=expiry,
                    cvv=cvv,
                    quotation=quotation,
                    customer=quotation.customer,
                    user=request.user,
                )
                issued_policy = payment.policy
            else:
                # Direct conversion
                issued_policy = PolicyService.issue_policy_from_quotation(
                    quotation=quotation,
                    underwriter=None,
                )

            messages.success(
                request,
                f"Congratulations! Policy '{issued_policy.policy_number}' has been issued and is now ACTIVE."
            )
            return redirect('policies:detail', pk=issued_policy.pk)

        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('quotations:convert', pk=quotation.pk)
        except Exception as e:
            messages.error(request, f"Policy issuance error: {str(e)}")
            return redirect('quotations:convert', pk=quotation.pk)
