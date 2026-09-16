from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.http import Http404

from core.permissions import CustomerRequiredMixin
from vehicles.models import Vehicle, VehicleType, FuelType, UsageType
from vehicles.services.vehicle_service import VehicleService
from vehicles.selectors import get_vehicle_by_id, get_customer_vehicles
from core.services import ServiceValidationError


class VehicleListView(CustomerRequiredMixin, ListView):
    """
    Renders the authenticated customer's vehicle garage with
    active status and linked insurance policies.
    """
    model = Vehicle
    template_name = 'customers/vehicles.html'
    context_object_name = 'vehicles'

    def get_queryset(self):
        customer = getattr(self.request.user, 'customer_profile', None)
        if not customer:
            return Vehicle.objects.none()
        return Vehicle.objects.filter(customer=customer).prefetch_related('policies__coverage_plan').order_by('-created_at')


class VehicleCreateView(CustomerRequiredMixin, View):
    """
    Registers a new vehicle asset under the customer profile.
    """
    template_name = 'vehicles/vehicle_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'vehicle_types': VehicleType.choices,
            'fuel_types': FuelType.choices,
            'usage_types': UsageType.choices,
        })

    def post(self, request):
        customer = getattr(request.user, 'customer_profile', None)
        if not customer:
            messages.error(request, "Customer profile not found.")
            return redirect('accounts:profile')

        try:
            vehicle = VehicleService.create_vehicle(customer, request.POST)
            messages.success(request, f"Vehicle '{vehicle.make} {vehicle.model}' ({vehicle.registration_number}) registered successfully!")
            return redirect('customers:vehicles')
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {
                'vehicle_types': VehicleType.choices,
                'fuel_types': FuelType.choices,
                'usage_types': UsageType.choices,
                'data': request.POST,
            })


class VehicleDetailView(LoginRequiredMixin, View):
    """
    Displays comprehensive vehicle specifications, insurance protection status,
    quotation history, and ownership context.
    Enforces strict customer isolation: Customer A cannot view Customer B's vehicle.
    """
    template_name = 'vehicles/vehicle_detail.html'

    def get(self, request, pk):
        vehicle = get_vehicle_by_id(pk)
        if not vehicle:
            raise Http404("Vehicle not found.")

        # Authorization: Customer can only view their own vehicle; Staff/Admin can view
        if request.user.is_customer:
            customer = getattr(request.user, 'customer_profile', None)
            if not customer or vehicle.customer != customer:
                raise PermissionDenied("Unauthorized: You do not have permission to view this vehicle.")
        elif not (request.user.is_underwriter or request.user.is_claims_handler or request.user.is_administrator or request.user.is_superuser):
            raise PermissionDenied("Unauthorized access.")

        active_policy = vehicle.policies.filter(status='ACTIVE').select_related('coverage_plan').first()
        quotations = vehicle.quotations.select_related('coverage_plan').order_by('-created_at')[:10]

        return render(request, self.template_name, {
            'vehicle': vehicle,
            'active_policy': active_policy,
            'quotations': quotations,
            'has_active_policy': bool(active_policy),
        })


class VehicleUpdateView(CustomerRequiredMixin, View):
    """
    Allows a customer to edit their registered vehicle specifications.
    If an active policy covers the vehicle, the registration number and IDV
    are strictly locked, preventing mid-term financial alteration.
    """
    template_name = 'vehicles/vehicle_edit.html'

    def get(self, request, pk):
        customer = getattr(request.user, 'customer_profile', None)
        vehicle = get_vehicle_by_id(pk)
        if not vehicle:
            raise Http404("Vehicle not found.")

        if vehicle.customer != customer and not (request.user.is_administrator or request.user.is_superuser):
            raise PermissionDenied("Unauthorized: You may only edit vehicles registered to your account.")

        active_policy = vehicle.policies.filter(status='ACTIVE').select_related('coverage_plan').first()

        return render(request, self.template_name, {
            'vehicle': vehicle,
            'active_policy': active_policy,
            'has_active_policy': bool(active_policy),
            'vehicle_types': VehicleType.choices,
            'fuel_types': FuelType.choices,
            'usage_types': UsageType.choices,
        })

    def post(self, request, pk):
        customer = getattr(request.user, 'customer_profile', None)
        vehicle = get_vehicle_by_id(pk)
        if not vehicle:
            raise Http404("Vehicle not found.")

        if vehicle.customer != customer and not (request.user.is_administrator or request.user.is_superuser):
            raise PermissionDenied("Unauthorized: You may only edit vehicles registered to your account.")

        try:
            updated_vehicle = VehicleService.update_vehicle(
                vehicle=vehicle,
                customer=vehicle.customer,
                data=request.POST,
                actor=request.user,
            )
            messages.success(request, f"Vehicle '{updated_vehicle.make} {updated_vehicle.model}' updated successfully!")
            return redirect('vehicles:detail', pk=updated_vehicle.pk)
        except ServiceValidationError as e:
            messages.error(request, str(e))
            active_policy = vehicle.policies.filter(status='ACTIVE').select_related('coverage_plan').first()
            return render(request, self.template_name, {
                'vehicle': vehicle,
                'active_policy': active_policy,
                'has_active_policy': bool(active_policy),
                'vehicle_types': VehicleType.choices,
                'fuel_types': FuelType.choices,
                'usage_types': UsageType.choices,
                'data': request.POST,
            })


class VehicleDeactivateView(CustomerRequiredMixin, View):
    """
    Deactivates / archives a customer's vehicle asset.
    Rejects deactivation if an active insurance policy is currently binding.
    """
    def post(self, request, pk):
        customer = getattr(request.user, 'customer_profile', None)
        vehicle = get_vehicle_by_id(pk)
        if not vehicle:
            raise Http404("Vehicle not found.")

        if vehicle.customer != customer and not (request.user.is_administrator or request.user.is_superuser):
            raise PermissionDenied("Unauthorized: You may only deactivate vehicles registered to your account.")

        try:
            VehicleService.deactivate_vehicle(
                vehicle=vehicle,
                customer=vehicle.customer,
                actor=request.user,
            )
            messages.success(request, f"Vehicle '{vehicle.make} {vehicle.model}' ({vehicle.registration_number}) has been deactivated.")
            return redirect('customers:vehicles')
        except ServiceValidationError as e:
            messages.error(request, str(e))
            return redirect('vehicles:detail', pk=vehicle.pk)
