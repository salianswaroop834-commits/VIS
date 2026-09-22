import json
from datetime import date, timedelta
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from core.permissions import CustomerRequiredMixin
from apps.policies.models import Policy
from apps.vehicles.models import Vehicle
from apps.claims.models import Claim, ClaimStatus
from apps.service_requests.models import ServiceRequest
from apps.customers.models import CustomerProfile, KYCVerification, KYCStatus, CustomerFeedback
from apps.customers.services.pan_verification_service import PanVerificationService
from core.services import ServiceValidationError


class CustomerDashboardView(CustomerRequiredMixin, TemplateView):
    """
    Live customer dashboard summarizing active policies, renewal alerts,
    registered vehicles, open claims pipeline, and service requests.
    """
    template_name = 'customers/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = getattr(self.request.user, 'customer_profile', None)
        if customer:
            policies = Policy.objects.filter(customer=customer).select_related('vehicle', 'coverage_plan')
            vehicles = Vehicle.objects.filter(customer=customer)
            claims = Claim.objects.filter(customer=customer).select_related('policy__vehicle').order_by('-created_at')
            srv_requests = ServiceRequest.objects.filter(customer=customer).order_by('-created_at')

            active_policies = policies.filter(is_active=True)
            today = date.today()
            expiring_soon = [p for p in active_policies if 0 <= (p.end_date - today).days <= 30]
            open_claims = claims.filter(status__in=[ClaimStatus.PENDING, ClaimStatus.IN_REVIEW])
            active_kyc = KYCVerification.objects.filter(user=self.request.user, status=KYCStatus.VERIFIED).first()
            active_assignment = customer.staff_assignments.filter(status='ACTIVE').select_related('staff').first()

            ctx['customer'] = customer
            ctx['policies'] = active_policies
            ctx['expiring_soon'] = expiring_soon
            ctx['vehicles'] = vehicles
            ctx['recent_claims'] = claims[:5]
            ctx['service_requests'] = srv_requests[:5]
            ctx['active_policies_count'] = active_policies.count()
            ctx['vehicles_count'] = vehicles.count()
            ctx['open_claims_count'] = open_claims.count()
            ctx['service_requests_count'] = srv_requests.filter(status='SUBMITTED').count()
            ctx['active_kyc'] = active_kyc
            ctx['active_assignment'] = active_assignment
        else:
            ctx['policies'] = []
            ctx['expiring_soon'] = []
            ctx['vehicles'] = []
            ctx['recent_claims'] = []
            ctx['service_requests'] = []
            ctx['active_policies_count'] = 0
            ctx['vehicles_count'] = 0
            ctx['open_claims_count'] = 0
            ctx['service_requests_count'] = 0
            ctx['active_kyc'] = None
            ctx['active_assignment'] = None
        return ctx


class CustomerPolicyListView(CustomerRequiredMixin, TemplateView):
    template_name = 'customers/policies.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = getattr(self.request.user, 'customer_profile', None)
        ctx['policies'] = Policy.objects.filter(customer=customer).select_related('vehicle', 'coverage_plan') if customer else []
        return ctx


class CustomerClaimListView(CustomerRequiredMixin, TemplateView):
    template_name = 'customers/claims.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = getattr(self.request.user, 'customer_profile', None)
        if customer:
            context['claims'] = Claim.objects.filter(customer=customer).select_related(
                'policy__vehicle', 'policy__coverage_plan', 'handler__user'
            ).order_by('-created_at')
        else:
            context['claims'] = []
        return context


class CustomerVehicleListView(CustomerRequiredMixin, TemplateView):
    template_name = 'customers/vehicles.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = getattr(self.request.user, 'customer_profile', None)
        ctx['vehicles'] = Vehicle.objects.filter(customer=customer) if customer else []
        return ctx


class CustomerKycView(CustomerRequiredMixin, View):
    """Renders KYC & PAN verification workspace."""
    template_name = 'customers/kyc_verify.html'

    def get(self, request):
        customer = getattr(request.user, 'customer_profile', None)
        latest_kyc = KYCVerification.objects.filter(user=request.user).order_by('-created_at').first()
        return render(request, self.template_name, {
            'customer': customer,
            'latest_kyc': latest_kyc,
            'is_verified': customer.is_identity_verified if customer else False,
        })


class CustomerKycPanInitiateView(CustomerRequiredMixin, View):
    """AJAX endpoint to initiate PAN lookup and trigger Firebase OTP."""

    def post(self, request):
        pan_number = request.POST.get('pan_number') or ''
        if not pan_number and request.body:
            try:
                body = json.loads(request.body)
                pan_number = body.get('pan_number', '')
            except Exception:
                pass

        ip_address = request.META.get('REMOTE_ADDR')
        try:
            result = PanVerificationService.initiate_pan_verification(
                user=request.user,
                pan_number=pan_number,
                actor_ip=ip_address,
            )
            return JsonResponse({'success': True, **result})
        except ServiceValidationError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class CustomerKycPanConfirmView(CustomerRequiredMixin, View):
    """AJAX endpoint to confirm OTP and finalize PAN KYC."""

    def post(self, request):
        data = request.POST
        if not data and request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}

        verification_id = data.get('verification_id', '')
        challenge_id = data.get('challenge_id', '')
        otp_code = data.get('otp_code', '')

        ip_address = request.META.get('REMOTE_ADDR')
        try:
            result = PanVerificationService.confirm_pan_otp(
                user=request.user,
                verification_id=verification_id,
                challenge_id=challenge_id,
                otp_code=otp_code,
                actor_ip=ip_address,
            )
            return JsonResponse({'success': True, **result})
        except ServiceValidationError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class CustomerFeedbackSubmitView(CustomerRequiredMixin, View):
    """Saves Net Promoter Score (NPS) customer feedback."""

    def post(self, request):
        try:
            score = int(request.POST.get('nps_score', 10))
            comment = request.POST.get('comment', '').strip()
            CustomerFeedback.objects.create(
                user=request.user,
                nps_score=max(0, min(10, score)),
                comment=comment,
            )
            messages.success(request, "Thank you for sharing your feedback!")
        except Exception as e:
            messages.error(request, "Could not record feedback.")
        return redirect('customers:dashboard')
