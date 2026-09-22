from django.urls import path
from .views import AuditLogListView, AuditLogDetailView

app_name = 'audit'

urlpatterns = [
    path('', AuditLogListView.as_view(), name='list'),
    path('<uuid:pk>/', AuditLogDetailView.as_view(), name='detail'),
]
