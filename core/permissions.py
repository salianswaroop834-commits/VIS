"""
Role-Based Access Control (RBAC) Permissions, Object-Level Authorization, & View Decorators.
Enforces 3-role hierarchy (USER, STAFF, ADMIN) with STAFF specializations (Underwriting, Claims)
and persistent Staff-Customer assignment access control.
"""

from functools import wraps
from typing import List, Union
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from rest_framework import permissions


class RoleRequiredMixin(AccessMixin):
    """CBV Mixin to restrict view access to specific authorized roles or properties."""
    allowed_roles: List[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if self.allowed_roles:
            user_role = getattr(request.user, 'role', '')
            if user_role not in self.allowed_roles and not any(
                (r in ('UNDERWRITER', 'STAFF') and request.user.is_underwriter) or
                (r in ('CLAIMS_HANDLER', 'STAFF') and request.user.is_claims_handler) or
                (r in ('ADMINISTRATOR', 'ADMIN') and request.user.is_administrator) or
                (r in ('CUSTOMER', 'USER') and request.user.is_customer)
                for r in self.allowed_roles
            ):
                raise PermissionDenied("You do not have the required operational permissions to access this page.")

        return super().dispatch(request, *args, **kwargs)


class CustomerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['USER', 'CUSTOMER']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_customer or request.user.is_superuser):
            raise PermissionDenied("You do not have customer permissions to access this portal.")
        return super().dispatch(request, *args, **kwargs)


class UnderwriterRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['STAFF', 'ADMIN', 'UNDERWRITER', 'ADMINISTRATOR']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_underwriter or request.user.is_administrator):
            raise PermissionDenied("You do not have Underwriting operational permissions.")
        return super().dispatch(request, *args, **kwargs)


class ClaimsHandlerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['STAFF', 'ADMIN', 'CLAIMS_HANDLER', 'ADMINISTRATOR']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_claims_handler or request.user.is_administrator):
            raise PermissionDenied("You do not have Claims Handling operational permissions.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['ADMIN', 'ADMINISTRATOR']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_administrator:
            raise PermissionDenied("You do not have administrative permissions.")
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['STAFF', 'ADMIN', 'UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_staff_member or request.user.is_administrator):
            raise PermissionDenied("You do not have employee/staff permissions.")
        return super().dispatch(request, *args, **kwargs)


def role_required(allowed_roles: Union[str, List[str]]):
    """
    Decorator for function-based views or methods to enforce role authorization.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/auth/login/?next={request.path}")

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_role = getattr(request.user, 'role', '')
            permitted = user_role in allowed_roles or any(
                (r in ('UNDERWRITER', 'STAFF') and request.user.is_underwriter) or
                (r in ('CLAIMS_HANDLER', 'STAFF') and request.user.is_claims_handler) or
                (r in ('ADMINISTRATOR', 'ADMIN') and request.user.is_administrator) or
                (r in ('CUSTOMER', 'USER') and request.user.is_customer)
                for r in allowed_roles
            )

            if not permitted:
                raise PermissionDenied("Unauthorized: Role not permitted.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


customer_required = role_required(['USER', 'CUSTOMER'])
underwriter_required = role_required(['STAFF', 'ADMIN', 'UNDERWRITER', 'ADMINISTRATOR'])
claims_handler_required = role_required(['STAFF', 'ADMIN', 'CLAIMS_HANDLER', 'ADMINISTRATOR'])
admin_required = role_required(['ADMIN', 'ADMINISTRATOR'])
staff_required = role_required(['STAFF', 'ADMIN', 'UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR'])


# --- Django REST Framework & Object-Level Permission Classes ---

class IsCustomerUser(permissions.BasePermission):
    """Allows access only to authenticated Customers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_customer)


class IsUnderwriterUser(permissions.BasePermission):
    """Allows access to Underwriters and Admins."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_underwriter or request.user.is_administrator))


class IsClaimsHandlerUser(permissions.BasePermission):
    """Allows access to Claims Handlers and Admins."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_claims_handler or request.user.is_administrator))


class IsAdministratorUser(permissions.BasePermission):
    """Allows access only to Administrators."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_administrator)


class IsAssignedStaffOrAdmin(permissions.BasePermission):
    """
    Object-level permission:
    - Customer owns the object -> Granted
    - Admin / Superuser -> Granted
    - Staff member -> Granted ONLY IF customer is actively assigned to this staff member
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_administrator or request.user.is_superuser:
            return True

        # Resolve target customer profile
        customer = None
        if hasattr(obj, 'customer'):
            customer = obj.customer
        elif hasattr(obj, 'user') and hasattr(obj.user, 'customer_profile'):
            customer = obj.user.customer_profile
        elif obj.__class__.__name__ == 'CustomerProfile':
            customer = obj

        if request.user.is_customer:
            return bool(customer and customer.user == request.user)

        if request.user.is_staff_member and customer:
            from apps.staff.models import StaffCustomerAssignment
            return StaffCustomerAssignment.objects.filter(
                staff=request.user,
                customer=customer,
                status='ACTIVE'
            ).exists()

        return False


# Compatibility alias
IsOwnerOrStaff = IsAssignedStaffOrAdmin
