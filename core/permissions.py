"""
Role-Based Access Control (RBAC) Permissions & View Decorators.
Enforces authorization at the application layer to complement Supabase Row Level Security.
"""

from functools import wraps
from typing import List, Union
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from rest_framework import permissions


class RoleRequiredMixin(AccessMixin):
    """CBV Mixin to restrict view access to specific authorized roles."""
    allowed_roles: List[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if self.allowed_roles and request.user.role not in self.allowed_roles and not request.user.is_superuser:
            raise PermissionDenied("You do not have the required operational permissions to access this page.")

        return super().dispatch(request, *args, **kwargs)


class CustomerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['CUSTOMER']


class UnderwriterRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['UNDERWRITER', 'ADMINISTRATOR']


class ClaimsHandlerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['CLAIMS_HANDLER', 'ADMINISTRATOR']


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['ADMINISTRATOR']


class StaffRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['UNDERWRITER', 'CLAIMS_HANDLER', 'ADMINISTRATOR']


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

            if request.user.role not in allowed_roles and not request.user.is_superuser:
                raise PermissionDenied("Unauthorized: Role not permitted.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


customer_required = role_required(['CUSTOMER'])
underwriter_required = role_required(['UNDERWRITER', 'ADMINISTRATOR'])
claims_handler_required = role_required(['CLAIMS_HANDLER', 'ADMINISTRATOR'])
admin_required = role_required(['ADMINISTRATOR'])


# --- Django REST Framework Permission Classes ---

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


class IsOwnerOrStaff(permissions.BasePermission):
    """
    Object-level permission: allows owners of an object (customer) or authorized staff.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff or request.user.is_administrator or request.user.is_underwriter or request.user.is_claims_handler:
            return True

        # Check customer object association
        if hasattr(obj, 'customer') and hasattr(obj.customer, 'user'):
            return obj.customer.user == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user

        return False
