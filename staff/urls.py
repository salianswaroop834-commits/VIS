from django.urls import path
from .views import (
    UnderwriterDashboardView,
    UnderwriterCustomerSearchView,
    UnderwriterPolicyCreateView,
    ClaimsHandlerDashboardView,
    AdminDashboardView,
    AdminCustomerAssignmentView,
    StaffMyCustomersView,
    StaffListView,
)

app_name = 'staff'

urlpatterns = [
    path('my-customers/', StaffMyCustomersView.as_view(), name='my-customers'),
    path('underwriter/dashboard/', UnderwriterDashboardView.as_view(), name='underwriter-dashboard'),
    path('underwriter/customers/', UnderwriterCustomerSearchView.as_view(), name='underwriter-customers'),
    path('underwriter/policies/create/', UnderwriterPolicyCreateView.as_view(), name='underwriter-policy-create'),
    path('claims-handler/dashboard/', ClaimsHandlerDashboardView.as_view(), name='claims-handler-dashboard'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('admin/assign-customer/', AdminCustomerAssignmentView.as_view(), name='admin-assign-customer'),
    path('management/', StaffListView.as_view(), name='staff-list'),
]
