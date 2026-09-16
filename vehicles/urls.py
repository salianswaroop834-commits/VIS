from django.urls import path
from .views import (
    VehicleListView,
    VehicleCreateView,
    VehicleDetailView,
    VehicleUpdateView,
    VehicleDeactivateView,
)

app_name = 'vehicles'

urlpatterns = [
    path('', VehicleListView.as_view(), name='list'),
    path('add/', VehicleCreateView.as_view(), name='create'),
    path('<uuid:pk>/', VehicleDetailView.as_view(), name='detail'),
    path('<uuid:pk>/edit/', VehicleUpdateView.as_view(), name='edit'),
    path('<uuid:pk>/deactivate/', VehicleDeactivateView.as_view(), name='deactivate'),
]
