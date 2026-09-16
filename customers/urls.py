from django.urls import path
from .views import (
    CustomerDashboardView,
    CustomerPolicyListView,
    CustomerClaimListView,
    CustomerVehicleListView,
)

app_name = 'customers'

urlpatterns = [
    path('dashboard/', CustomerDashboardView.as_view(), name='dashboard'),
    path('policies/', CustomerPolicyListView.as_view(), name='policies'),
    path('claims/', CustomerClaimListView.as_view(), name='claims'),
    path('vehicles/', CustomerVehicleListView.as_view(), name='vehicles'),
]
