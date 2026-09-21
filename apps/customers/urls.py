from django.urls import path
from .views import (
    CustomerDashboardView,
    CustomerPolicyListView,
    CustomerClaimListView,
    CustomerVehicleListView,
    CustomerKycView,
    CustomerKycPanInitiateView,
    CustomerKycPanConfirmView,
    CustomerFeedbackSubmitView,
)

app_name = 'customers'

urlpatterns = [
    path('dashboard/', CustomerDashboardView.as_view(), name='dashboard'),
    path('policies/', CustomerPolicyListView.as_view(), name='policies'),
    path('claims/', CustomerClaimListView.as_view(), name='claims'),
    path('vehicles/', CustomerVehicleListView.as_view(), name='vehicles'),
    path('kyc/', CustomerKycView.as_view(), name='kyc-verify'),
    path('kyc/pan/initiate/', CustomerKycPanInitiateView.as_view(), name='kyc-pan-initiate'),
    path('kyc/pan/confirm/', CustomerKycPanConfirmView.as_view(), name='kyc-pan-confirm'),
    path('feedback/', CustomerFeedbackSubmitView.as_view(), name='feedback-submit'),
]
