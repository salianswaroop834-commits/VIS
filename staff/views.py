from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, View, ListView
from django.contrib import messages
from django.urls import reverse
from core.permissions import (
    UnderwriterRequiredMixin,
    ClaimsHandlerRequiredMixin,
    AdminRequiredMixin,
)
from staff.models import StaffProfile
from customers.models import CustomerProfile
from customers.services.customer_service import CustomerService
from policies.models import Policy
from policies.services.policy_service import PolicyService
from quotations.models import CoveragePlan
from quotations.services.quotation_service import QuotationService
from vehicles.models import Vehicle
from core.services import ServiceValidationError


class UnderwriterDashboardView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_dashboard.html'

    def get(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        query = request.GET.get('q', '')

        policies = PolicyService.search_policies(query, underwriter=staff)
        active_count = policies.filter(status='ACTIVE').count()
        total_premium = sum(p.premium_amount for p in policies.filter(status='ACTIVE'))

        return render(request, self.template_name, {
            'staff': staff,
            'policies': policies[:50],
            'active_count': active_count,
            'total_premium': total_premium,
            'query': query,
        })


class UnderwriterCustomerSearchView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_customers.html'

    def get(self, request):
        query = request.GET.get('q', '')
        customers = CustomerService.search_customers_by_identifier(query)
        return render(request, self.template_name, {
            'customers': customers,
            'query': query,
        })

    def post(self, request):
        staff = getattr(request.user, 'staff_profile', None)
        try:
            profile = CustomerService.register_customer_for_underwriting(request.POST, underwriter=staff)
            messages.success(request, f"Customer '{profile.user.email}' ({profile.customer_code}) registered successfully!")
            return redirect(f"{reverse('staff:underwriter-customers')}?q={profile.customer_code}")
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {
                'customers': CustomerService.search_customers_by_identifier(''),
                'form_data': request.POST,
            })


class UnderwriterPolicyCreateView(UnderwriterRequiredMixin, View):
    template_name = 'staff/underwriter_policy_create.html'

    def get(self, request):
        QuotationService.seed_default_plans()
        plans = CoveragePlan.objects.filter(is_active=True).order_by('base_rate_percentage')
        customers = CustomerProfile.objects.select_related('user').all()[:100]
        vehicles = Vehicle.objects.select_related('customer__user').all()[:100]

        return render(request, self.template_name, {
            'plans': plans,
            'customers': customers,
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


from django.db.models import Sum
from accounts.models import User
from claims.models import Claim, ClaimStatus
from audit.models import AuditLog
from predictions.services.mlops_service import MlopsService


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

        approval_limit = staff.max_claim_approval_limit if staff else Decimal('5000.00')

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
            'recent_audits': recent_audits,
            'mlops_summary': mlops_summary,
            'governance': governance,
        })


class StaffListView(AdminRequiredMixin, TemplateView):
    template_name = 'staff/staff_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['staff_members'] = StaffProfile.objects.select_related('user').all().order_by('staff_code')
        return ctx

