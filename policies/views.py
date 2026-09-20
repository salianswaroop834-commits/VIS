from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from policies.models import Policy, PolicyStatus
from policies.services.policy_service import PolicyService
from staff.models import StaffCustomerAssignment
from staff.services.assignment_service import StaffAssignmentService
from core.services import ServiceValidationError


def _check_policy_access(user, policy: Policy):
    """Enforces customer ownership or active staff assignment check."""
    if user.is_administrator or user.is_superuser:
        return
    if user.is_customer:
        customer = getattr(user, 'customer_profile', None)
        if not customer or policy.customer != customer:
            raise PermissionDenied("You are not authorized to access this policy.")
        return
    if user.is_staff_member:
        staff_prof = getattr(user, 'staff_profile', None)
        if staff_prof and policy.assigned_staff == staff_prof:
            return
        is_assigned = StaffCustomerAssignment.objects.filter(
            staff=user,
            customer=policy.customer,
            status='ACTIVE'
        ).exists()
        if not is_assigned:
            raise PermissionDenied("Unauthorized: This policy belongs to a customer not assigned to you.")
        return
    raise PermissionDenied("Insufficient privileges to access this policy.")


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
        elif user.is_staff_member:
            assigned_customers = StaffAssignmentService.get_assigned_customers(user)
            return Policy.objects.filter(customer__in=assigned_customers).select_related('customer__user', 'vehicle', 'coverage_plan')
        elif user.is_administrator or user.is_superuser:
            return Policy.objects.all().select_related('customer__user', 'vehicle', 'coverage_plan')
        return Policy.objects.none()


class PolicyDetailView(LoginRequiredMixin, DetailView):
    model = Policy
    template_name = 'policies/policy_detail.html'
    context_object_name = 'policy'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        _check_policy_access(self.request.user, obj)
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
        _check_policy_access(request.user, policy)

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
        _check_policy_access(request.user, policy)

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
        _check_policy_access(request.user, policy)

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
        _check_policy_access(request.user, policy)

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
    def post(self, request, pk=None, request_pk=None):
        from service_requests.models import ServiceRequest
        srv_id = request_pk or pk or request.POST.get('service_request_id')
        srv = get_object_or_404(ServiceRequest, pk=srv_id)
        policy = srv.policy
        _check_policy_access(request.user, policy)

        # RBAC check: only underwriter or admin can adjudicate endorsements
        if not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("Unauthorized: Only underwriters or administrators may adjudicate endorsements.")

        action = request.POST.get('decision') or request.POST.get('action')  # 'APPROVE' or 'REJECT'
        notes = request.POST.get('notes') or request.POST.get('resolution_notes', '')

        try:
            if action in ('APPROVE', 'APPROVED'):
                PolicyService.approve_endorsement_request(
                    service_request=srv,
                    underwriter_user=request.user,
                    notes=notes,
                )
                messages.success(request, f"Endorsement '{srv.request_number}' approved and applied to policy.")
            elif action in ('REJECT', 'REJECTED'):
                PolicyService.reject_endorsement_request(
                    service_request=srv,
                    underwriter_user=request.user,
                    notes=notes,
                )
                messages.warning(request, f"Endorsement '{srv.request_number}' was rejected.")
            else:
                messages.error(request, "Invalid endorsement adjudication action.")
        except ServiceValidationError as e:
            messages.error(request, str(e))

        return redirect('policies:detail', pk=policy.pk)
