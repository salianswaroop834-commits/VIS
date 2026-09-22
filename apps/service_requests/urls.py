from django.urls import path
from .views import (
    ServiceRequestListView,
    ServiceRequestCreateView,
    ServiceRequestDetailView,
    ServiceRequestUpdateStatusView,
)

app_name = 'service_requests'

urlpatterns = [
    path('', ServiceRequestListView.as_view(), name='list'),
    path('new/', ServiceRequestCreateView.as_view(), name='create'),
    path('<uuid:pk>/', ServiceRequestDetailView.as_view(), name='detail'),
    path('<uuid:pk>/update-status/', ServiceRequestUpdateStatusView.as_view(), name='update_status'),
]
