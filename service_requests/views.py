from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from core.permissions import CustomerRequiredMixin, StaffRequiredMixin
from service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType
from service_requests.services.service_request_service import ServiceRequestService
from policies.models import Policy
from core.services import ServiceValidationError


class ServiceRequestListView(LoginRequiredMixin, ListView):
    """Lists servicing requests according to user role."""
    model = ServiceRequest
    template_name = 'service_requests/request_list.html'
    context_object_name = 'requests'

    def get_queryset(self):
        user = self.request.user
        if user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if not customer:
                return ServiceRequest.objects.none()
            return ServiceRequest.objects.filter(customer=customer).select_related('policy__vehicle', 'assigned_staff')
        # Staff and admins view all service requests
        status_filter = self.request.GET.get('status')
        qs = ServiceRequest.objects.all().select_related('customer__user', 'policy__vehicle', 'assigned_staff')
        if status_filter and status_filter in ServiceRequestStatus.values:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = ServiceRequestStatus.choices
        context['selected_status'] = self.request.GET.get('status', '')
        return context


class ServiceRequestCreateView(CustomerRequiredMixin, View):
    template_name = 'service_requests/request_form.html'

    def get(self, request):
        customer = getattr(request.user, 'customer_profile', None)
        policies = Policy.objects.filter(customer=customer, status='ACTIVE').select_related('vehicle')
        return render(request, self.template_name, {
            'policies': policies,
            'request_types': ServiceRequestType.choices,
        })

    def post(self, request):
        customer = getattr(request.user, 'customer_profile', None)
        if not customer:
            raise PermissionDenied("Customer profile required to submit a service request.")

        try:
            req_type = request.POST.get('request_type')
            title = request.POST.get('title')
            description = request.POST.get('description')
            policy_id = request.POST.get('policy_id')

            policy = None
            if policy_id:
                policy = get_object_or_404(Policy, pk=policy_id)
                if policy.customer != customer:
                    raise PermissionDenied("Unauthorized: You may only file service requests against your own policies.")

            srv = ServiceRequestService.create_service_request(
                customer=customer,
                request_type=req_type,
                title=title,
                description=description,
                policy=policy,
            )
            messages.success(request, f"Service request '{srv.request_number}' submitted successfully.")
            return redirect('service_requests:detail', pk=srv.pk)

        except PermissionDenied:
            raise
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('service_requests:create')
        except Exception as e:
            messages.error(request, f"Failed to submit service request: {str(e)}")
            return redirect('service_requests:create')


class ServiceRequestDetailView(LoginRequiredMixin, DetailView):
    model = ServiceRequest
    template_name = 'service_requests/request_detail.html'
    context_object_name = 'req'

    def get_object(self, queryset=None):
        req = super().get_object(queryset)
        user = self.request.user
        if user.is_customer:
            customer = getattr(user, 'customer_profile', None)
            if not customer or req.customer != customer:
                raise PermissionDenied("You are not authorized to view this service request.")
        elif not (user.is_underwriter or user.is_claims_handler or user.is_administrator):
            raise PermissionDenied("Insufficient privileges to view this service request.")
        return req

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = ServiceRequestStatus.choices
        context['can_manage'] = (
            self.request.user.is_underwriter or
            self.request.user.is_claims_handler or
            self.request.user.is_administrator
        )
        return context


class ServiceRequestUpdateStatusView(StaffRequiredMixin, View):
    """Staff actions on a service request (progressing or resolving)."""
    def post(self, request, pk):
        srv = get_object_or_404(ServiceRequest, pk=pk)
        new_status = request.POST.get('status')
        notes = request.POST.get('resolution_notes', '')

        try:
            ServiceRequestService.update_status(
                service_request=srv,
                staff_user=request.user,
                new_status=new_status,
                resolution_notes=notes,
            )
            messages.success(request, f"Service request '{srv.request_number}' updated to {srv.get_status_display()}.")
        except ServiceValidationError as e:
            messages.error(request, str(e))

        return redirect('service_requests:detail', pk=srv.pk)

