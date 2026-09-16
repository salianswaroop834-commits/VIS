from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from policies.models import Policy, PolicyStatus
from policies.services.policy_service import PolicyService
from core.services import ServiceValidationError


class PolicyListView(LoginRequiredMixin, ListView):
    model = Policy
    template_name = 'customers/policies.html'
    context_object_name = 'policies'

    def get_queryset(self):
        user = self.request.user
        if user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if not customer:
                return Policy.objects.none()
            return Policy.objects.filter(customer=customer).select_related('vehicle', 'coverage_plan')
        elif user.is_underwriter:
            staff = getattr(user, 'staff_profile', None)
            return Policy.objects.filter(underwriter=staff).select_related('customer__user', 'vehicle', 'coverage_plan')
        elif user.is_administrator or user.is_claims_handler:
            return Policy.objects.all().select_related('customer__user', 'vehicle', 'coverage_plan')
        return Policy.objects.none()


class PolicyDetailView(LoginRequiredMixin, DetailView):
    model = Policy
    template_name = 'policies/policy_detail.html'
    context_object_name = 'policy'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if not customer or obj.customer != customer:
                raise PermissionDenied("You are not authorized to view this policy.")
        elif not (user.is_underwriter or user.is_administrator or user.is_claims_handler):
            raise PermissionDenied("Insufficient privileges to view this policy.")
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        policy = self.object
        context['service_requests'] = policy.service_requests.all().order_by('-created_at')
        context['can_cancel'] = (policy.status == PolicyStatus.ACTIVE)
        context['can_endorse'] = (policy.status == PolicyStatus.ACTIVE)
        context['can_renew'] = (
            policy.status in (PolicyStatus.ACTIVE, PolicyStatus.EXPIRED)
            and not policy.renewal_history.filter(status__in=[PolicyStatus.ACTIVE, PolicyStatus.RENEWED]).exists()
        )
        return context


class PolicyCertificateView(LoginRequiredMixin, View):
    """
    Generates and downloads policy certificate PDF.
    Enforces strict customer ownership isolation and RBAC.
    """
    def get(self, request, pk):
        policy = get_object_or_404(Policy, pk=pk)

        # RBAC and IDOR guard
        if request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if not customer or policy.customer != customer:
                raise PermissionDenied("You are not authorized to download this policy certificate.")
        elif not (request.user.is_underwriter or request.user.is_administrator or request.user.is_claims_handler):
            raise PermissionDenied("Insufficient privileges to access policy certificates.")

        pdf_bytes = PolicyService.generate_policy_certificate(policy, actor=request.user)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Nexisure_Certificate_{policy.policy_number}.pdf"'
        return response


class PolicyRenewView(LoginRequiredMixin, View):
    """
    Executes non-mutating policy renewal, issuing a new policy record
    and recording lineage against the existing policy.
    """
    def post(self, request, pk):
        policy = get_object_or_404(Policy, pk=pk)

        # Authorization: customer owning policy or underwriter/admin
        if request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if not customer or policy.customer != customer:
                raise PermissionDenied("Unauthorized: You may only renew your own policies.")
        elif not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("Insufficient privileges to renew policy.")

        try:
            duration = int(request.POST.get('duration_years', 1))
            new_policy = PolicyService.renew_policy(
                existing_policy=policy,
                duration_years=duration,
            )
            messages.success(
                request,
                f"Policy renewed successfully! New Policy '{new_policy.policy_number}' is now active."
            )
            return redirect('policies:detail', pk=new_policy.pk)
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('policies:detail', pk=policy.pk)


class PolicyCancelView(LoginRequiredMixin, View):
    """
    Formal cancellation endpoint for active policies.
    """
    def post(self, request, pk):
        policy = get_object_or_404(Policy, pk=pk)

        # IDOR check:
        if request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if not customer or policy.customer != customer:
                raise PermissionDenied("You are not authorized to cancel this policy.")
        elif not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("Insufficient privileges to cancel policy.")

        try:
            reason = request.POST.get('reason', '')
            PolicyService.cancel_policy(policy, actor=request.user, reason=reason)
            messages.success(request, f"Policy '{policy.policy_number}' has been cancelled successfully.")
        except ServiceValidationError as e:
            messages.error(request, str(e))

        return redirect('policies:detail', pk=policy.pk)


class PolicyEndorsementRequestView(LoginRequiredMixin, View):
    """
    Customer endpoint to submit a mid-term policy endorsement request.
    """
    def post(self, request, pk):
        policy = get_object_or_404(Policy, pk=pk)

        # IDOR check:
        if request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if not customer or policy.customer != customer:
                raise PermissionDenied("You are not authorized to request endorsements for this policy.")
        elif not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("Insufficient privileges to request endorsement.")

        endorsement_type = request.POST.get('endorsement_type')
        title = request.POST.get('title', f"Endorsement: {policy.policy_number}")
        description = request.POST.get('description', '')

        # Build requested_changes dict based on type
        requested_changes = {}
        if endorsement_type == 'ADDRESS_UPDATE':
            for key in ('address', 'city', 'postal_code'):
                val = request.POST.get(key, '').strip()
                if val:
                    requested_changes[key] = val
        elif endorsement_type == 'VEHICLE_UPDATE':
            for key in ('usage_type', 'color'):
                val = request.POST.get(key, '').strip()
                if val:
                    requested_changes[key] = val
        
        # Check if malicious input attempted to modify protected fields:
        for fin_key in ('premium_amount', 'deductible_amount', 'vehicle_value', 'idv', 'policy_number'):
            if fin_key in request.POST:
                requested_changes[fin_key] = request.POST.get(fin_key)

        try:
            srv = PolicyService.request_policy_endorsement(
                policy=policy,
                customer=policy.customer,
                endorsement_type=endorsement_type,
                requested_changes=requested_changes,
                title=title,
                description=description,
                actor=request.user,
            )
            messages.success(
                request,
                f"Endorsement request '{srv.request_number}' submitted successfully for underwriting review."
            )
        except ServiceValidationError as e:
            messages.error(request, str(e))

        return redirect('policies:detail', pk=policy.pk)


class PolicyEndorsementAdjudicateView(LoginRequiredMixin, View):
    """
    Staff/Underwriting endpoint to review and approve/reject endorsement requests.
    """
    def post(self, request, request_pk):
        from service_requests.models import ServiceRequest
        srv = get_object_or_404(ServiceRequest, pk=request_pk)

        # RBAC: Only Underwriter or Administrator
        if not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("Only Underwriters or Administrators can adjudicate endorsements.")

        # Self-approval guard
        if srv.customer.user == request.user:
            raise PermissionDenied("Customer cannot adjudicate their own endorsement request.")

        decision = request.POST.get('decision', '').upper()
        notes = request.POST.get('notes', '')

        try:
            PolicyService.adjudicate_endorsement(
                service_request=srv,
                reviewer=request.user,
                decision=decision,
                notes=notes,
            )
            messages.success(request, f"Endorsement request '{srv.request_number}' has been {decision}ED.")
        except ServiceValidationError as e:
            messages.error(request, str(e))

        if srv.policy:
            return redirect('policies:detail', pk=srv.policy.pk)
        return redirect('staff:admin_dashboard')
