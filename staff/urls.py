from django.urls import path
from .views import (
    UnderwriterDashboardView,
    UnderwriterCustomerSearchView,
    UnderwriterPolicyCreateView,
    ClaimsHandlerDashboardView,
    AdminDashboardView,
    StaffListView,
)

app_name = 'staff'

urlpatterns = [
    path('underwriter/dashboard/', UnderwriterDashboardView.as_view(), name='underwriter-dashboard'),
    path('underwriter/customers/', UnderwriterCustomerSearchView.as_view(), name='underwriter-customers'),
    path('underwriter/policies/create/', UnderwriterPolicyCreateView.as_view(), name='underwriter-policy-create'),
    path('claims-handler/dashboard/', ClaimsHandlerDashboardView.as_view(), name='claims-handler-dashboard'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('management/', StaffListView.as_view(), name='staff-list'),
]
