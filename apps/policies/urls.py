from django.urls import path
from .views import (
    PolicyListView,
    PolicyDetailView,
    PolicyRenewView,
    PolicyCertificateView,
    PolicyCancelView,
    PolicyEndorsementRequestView,
    PolicyEndorsementAdjudicateView,
)

app_name = 'policies'

urlpatterns = [
    path('', PolicyListView.as_view(), name='list'),
    path('<uuid:pk>/', PolicyDetailView.as_view(), name='detail'),
    path('<uuid:pk>/certificate/', PolicyCertificateView.as_view(), name='certificate'),
    path('<uuid:pk>/renew/', PolicyRenewView.as_view(), name='renew'),
    path('<uuid:pk>/cancel/', PolicyCancelView.as_view(), name='cancel'),
    path('<uuid:pk>/endorsement/', PolicyEndorsementRequestView.as_view(), name='endorsement_request'),
    path('endorsements/<uuid:request_pk>/adjudicate/', PolicyEndorsementAdjudicateView.as_view(), name='endorsement_adjudicate'),
]
