from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, View, ListView
from django.contrib import messages
from django.urls import reverse
from django.db.models import Sum, Q
from django.http import JsonResponse
from core.permissions import (
    UnderwriterRequiredMixin,
    ClaimsHandlerRequiredMixin,
    AdminRequiredMixin,
    StaffRequiredMixin,
)
from accounts.models import User
from staff.models import StaffProfile, StaffCustomerAssignment, AssignmentStatus
from staff.services.assignment_service import StaffAssignmentService
from customers.models import CustomerProfile
from customers.services.customer_service import CustomerService
from policies.models import Policy
from policies.services.policy_service import PolicyService
from quotations.models import CoveragePlan
from quotations.services.quotation_service import QuotationService
from vehicles.models import Vehicle
from claims.models import Claim, ClaimStatus
from audit.models import AuditLog
from predictions.services.mlops_service import MlopsService
from core.services import ServiceValidationError


class StaffMyCustomersView(StaffRequiredMixin, View):
    """
    Dedicated view for staff showing strictly their assigned customers,
    their vehicles, active policies, and recent claims.
    """
    template_name = 'staff/my_customers.html'

    def get(self, request):
        assigned_customers = StaffAssignmentService.get_assigned_customers(request.user)
        query = request.GET.get('q', '').strip()
        if query:
            assigned_customers = assigned_customers.filter(
                Q(customer_code__icontains=query) |
                Q(user__email__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            )

        return render(request, self.template_name, {
            'customers': assigned_customers,
            'query': query,
            'is_admin': request.user.is_administrator,
        })


class UnderwriterDashboardView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_dashboard.html'

    def get(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        query = request.GET.get('q', '')

        assigned_customers = StaffAssignmentService.get_assigned_customers(request.user)

        if request.user.is_administrator or request.user.is_superuser:
            policies = PolicyService.search_policies(query, underwriter=staff)
        else:
            policies = Policy.objects.filter(
                Q(customer__in=assigned_customers) | Q(assigned_staff=staff)
            ).select_related('customer__user', 'vehicle', 'coverage_plan')
            if query:
                policies = policies.filter(
                    Q(policy_number__icontains=query) |
                    Q(customer__customer_code__icontains=query) |
                    Q(vehicle__registration_number__icontains=query)
                )

        active_count = policies.filter(status='ACTIVE').count()
        total_premium = sum(p.premium_amount for p in policies.filter(status='ACTIVE'))

        return render(request, self.template_name, {
            'staff': staff,
            'policies': policies[:50],
            'active_count': active_count,
            'total_premium': total_premium,
            'query': query,
            'assigned_customers_count': assigned_customers.count(),
        })


class UnderwriterCustomerSearchView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_customers.html'

    def get(self, request):
        query = request.GET.get('q', '')
        if request.user.is_administrator or request.user.is_superuser:
            customers = CustomerService.search_customers_by_identifier(query)
        else:
            assigned = StaffAssignmentService.get_assigned_customers(request.user)
            if query:
                customers = assigned.filter(
                    Q(customer_code__icontains=query) |
                    Q(user__email__icontains=query) |
                    Q(first_name__icontains=query) |
                    Q(last_name__icontains=query)
                )
            else:
                customers = assigned[:50]

        return render(request, self.template_name, {
            'customers': customers,
            'query': query,
        })

    def post(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        try:
            profile = CustomerService.register_customer_for_underwriting(request.POST, underwriter=staff)
            # Automatically assign to registering staff member if staff
            if request.user.is_staff_member:
                StaffAssignmentService.assign_customer(
                    staff_user=request.user,
                    customer=profile,
                    assigned_by=request.user,
                    reason="Customer registered by underwriting staff",
                )
            messages.success(request, f"Customer '{profile.user.email}' ({profile.customer_code}) registered and assigned successfully!")
            return redirect(f"{reverse('staff:underwriter-customers')}?q={profile.customer_code}")
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {
                'customers': StaffAssignmentService.get_assigned_customers(request.user),
                'form_data': request.POST,
            })


class UnderwriterPolicyCreateView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_policy_create.html'

    def get(self, request):
        QuotationService.seed_default_plans()
        plans = CoveragePlan.objects.filter(is_active=True).order_by('base_rate_percentage')
        assigned_customers = StaffAssignmentService.get_assigned_customers(request.user)
        vehicles = Vehicle.objects.filter(customer__in=assigned_customers).select_related('customer__user')[:100]

        return render(request, self.template_name, {
            'plans': plans,
            'customers': assigned_customers[:100],
            'vehicles': vehicles,
        })

    def post(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        try:
            customer_id = request.POST.get('customer_id')
            vehicle_id = request.POST.get('vehicle_id')
            plan_code = request.POST.get('coverage_plan')
            duration_years = int(request.POST.get('duration_years', 1))

            customer = get_object_or_404(CustomerProfile, pk=customer_id)
            vehicle = get_object_or_404(Vehicle, pk=vehicle_id)

            # Security: Ensure staff is assigned to customer (or admin)
            if not request.user.is_administrator and not request.user.is_superuser:
                if not StaffAssignmentService.is_customer_assigned_to_staff(request.user, customer):
                    raise ServiceValidationError("You cannot issue policies for a customer not assigned to you.")

            draft = QuotationService.create_quotation_draft(
                vehicle_value=vehicle.vehicle_value,
                plan_code=plan_code,
                duration_years=duration_years,
                customer=customer,
                vehicle=vehicle,
            )

            policy = PolicyService.issue_policy_from_quotation(draft, underwriter=staff)
            messages.success(request, f"Policy '{policy.policy_number}' issued successfully for {customer.user.email}!")
            return redirect('policies:detail', pk=policy.pk)

        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('staff:underwriter-policy-create')
        except Exception as e:
            messages.error(request, f"Failed to issue policy: {str(e)}")
            return redirect('staff:underwriter-policy-create')


class ClaimsHandlerDashboardView(ClaimsHandlerRequiredMixin, View):
    """
    Operational command center for claims handlers.
    Displays shared pending queue, assigned in-review claims, and authority limit.
    """
    template_name = 'staff/claims_handler_dashboard.html'

    def get(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        pending_claims = Claim.objects.filter(status=ClaimStatus.PENDING, handler=None).select_related(
            'policy__vehicle', 'policy__customer__user'
        ).order_by('created_at')

        my_review_claims = Claim.objects.filter(status=ClaimStatus.IN_REVIEW, handler=staff).select_related(
            'policy__vehicle', 'policy__customer__user'
        ).order_by('-updated_at') if staff else []

        recent_decided = Claim.objects.filter(
            handler=staff,
            status__in=[ClaimStatus.APPROVED, ClaimStatus.REJECTED]
        ).order_by('-updated_at')[:10] if staff else []

        approval_limit = staff.max_claim_approval_limit if staff else Decimal('50000.00')

        return render(request, self.template_name, {
            'staff': staff,
            'pending_claims': pending_claims[:20],
            'my_review_claims': my_review_claims,
            'recent_decided': recent_decided,
            'pending_count': pending_claims.count(),
            'in_review_count': len(my_review_claims),
            'decided_count': len(recent_decided),
            'approval_limit': approval_limit,
        })


class AdminDashboardView(AdminRequiredMixin, View):
    """
    Executive administration dashboard.
    Tracks platform-wide policy revenue, claims loss ratio, staff workloads, and MLOps telemetry.
    """
    template_name = 'staff/admin_dashboard.html'

    def get(self, request):
        total_users = User.objects.count()
        active_policies = Policy.objects.filter(is_active=True)
        total_premium = active_policies.aggregate(Sum('premium_amount'))['premium_amount__sum'] or Decimal('0.00')

        all_claims = Claim.objects.all()
        settled_claims = all_claims.filter(status=ClaimStatus.APPROVED)
        total_settled = settled_claims.aggregate(Sum('settlement_amount'))['settlement_amount__sum'] or Decimal('0.00')

        loss_ratio = round(float(total_settled / total_premium * 100), 2) if total_premium > 0 else 0.0

        staff_members = StaffProfile.objects.select_related('user').all()
        all_customers = CustomerProfile.objects.select_related('user').all()
        recent_assignments = StaffCustomerAssignment.objects.select_related('staff', 'customer__user', 'assigned_by').order_by('-assigned_at')[:15]
        recent_audits = AuditLog.objects.order_by('-created_at')[:15]
        mlops_summary = MlopsService.get_registered_models_summary()
        governance = MlopsService.get_governance_metrics()

        return render(request, self.template_name, {
            'total_users': total_users,
            'active_policies_count': active_policies.count(),
            'total_premium': total_premium,
            'total_claims_count': all_claims.count(),
            'total_settled_amount': total_settled,
            'loss_ratio': loss_ratio,
            'staff_members': staff_members,
            'all_customers': all_customers,
            'recent_assignments': recent_assignments,
            'recent_audits': recent_audits,
            'mlops_summary': mlops_summary,
            'governance': governance,
        })


class AdminCustomerAssignmentView(AdminRequiredMixin, View):
    """
    Admin action to assign, transfer, or unassign customers to staff members.
    """
    def post(self, request):
        action = request.POST.get('action', 'assign')
        customer_id = request.POST.get('customer_id')
        staff_id = request.POST.get('staff_id')
        reason = request.POST.get('reason', '')
        notes = request.POST.get('notes', '')

        customer = get_object_or_404(CustomerProfile, pk=customer_id)

        try:
            if action == 'unassign':
                StaffAssignmentService.unassign_customer(
                    customer=customer,
                    assigned_by=request.user,
                    reason=reason or 'Unassigned by administrator',
                )
                messages.success(request, f"Customer {customer.customer_code} unassigned successfully.")
            elif action in ('assign', 'transfer'):
                staff_user = get_object_or_404(User, pk=staff_id)
                StaffAssignmentService.assign_customer(
                    staff_user=staff_user,
                    customer=customer,
                    assigned_by=request.user,
                    reason=reason,
                    notes=notes,
                )
                messages.success(request, f"Customer {customer.customer_code} assigned to {staff_user.email} successfully.")
        except ServiceValidationError as e:
            messages.error(request, str(e))

        return redirect('staff:admin-dashboard')


class StaffListView(AdminRequiredMixin, TemplateView):
    template_name = 'staff/staff_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['staff_members'] = StaffProfile.objects.select_related('user').all().order_by('staff_code')
        return ctx
