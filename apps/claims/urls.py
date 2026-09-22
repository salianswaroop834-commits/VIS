from django.urls import path
from .views import (
    ClaimQueueView,
    ClaimCreateView,
    ClaimDetailView,
    ClaimSelfAssignView,
    ClaimDecisionView,
    ClaimSettleView,
    ClaimDocumentUploadView,
    ClaimDocumentDownloadView,
)

app_name = 'claims'

urlpatterns = [
    path('queue/', ClaimQueueView.as_view(), name='queue'),
    path('file/', ClaimCreateView.as_view(), name='create'),
    path('<uuid:pk>/', ClaimDetailView.as_view(), name='detail'),
    path('<uuid:pk>/assign/', ClaimSelfAssignView.as_view(), name='self-assign'),
    path('<uuid:pk>/self-assign/', ClaimSelfAssignView.as_view(), name='assign'),  # Alias for backward compatibility
    path('<uuid:pk>/decision/', ClaimDecisionView.as_view(), name='decision'),
    path('<uuid:pk>/settle/', ClaimSettleView.as_view(), name='settle'),
    path('<uuid:pk>/documents/upload/', ClaimDocumentUploadView.as_view(), name='document-upload'),
    path('documents/<uuid:doc_pk>/download/', ClaimDocumentDownloadView.as_view(), name='document-download'),
]

