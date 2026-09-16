from datetime import date, timedelta
from django.views.generic import TemplateView
from core.permissions import CustomerRequiredMixin
from policies.models import Policy
from vehicles.models import Vehicle
from claims.models import Claim, ClaimStatus
from service_requests.models import ServiceRequest


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
