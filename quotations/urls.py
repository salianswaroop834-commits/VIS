from django.urls import path
from .views import (
    CustomerQuotationListView,
    CoverageComparisonView,
    QuotationCreateView,
    QuotationDetailView,
    QuotationAcceptView,
    QuotationConvertView,
)

app_name = 'quotations'

urlpatterns = [
    # Customer quotations dashboard
    path('', CustomerQuotationListView.as_view(), name='list'),

    # Coverage plans comparison
    path('plans/', CoverageComparisonView.as_view(), name='plans'),
    path('compare/', CoverageComparisonView.as_view(), name='compare'),

    # Quotation creation / estimator
    path('create/', QuotationCreateView.as_view(), name='create'),
    path('estimator/', QuotationCreateView.as_view(), name='estimator'),

    # UUID primary key routes (for reverse('quotations:detail', kwargs={'pk': ...}))
    path('<uuid:pk>/', QuotationDetailView.as_view(), name='detail'),
    path('<uuid:pk>/accept/', QuotationAcceptView.as_view(), name='accept'),
    path('<uuid:pk>/convert/', QuotationConvertView.as_view(), name='convert'),

    # Named string routes (for /quotations/view/QTE-2026-XXXX/)
    path('view/<str:quotation_number>/', QuotationDetailView.as_view(), name='detail_by_number'),
    path('view/<str:quotation_number>/accept/', QuotationAcceptView.as_view(), name='accept_by_number'),
    path('view/<str:quotation_number>/convert/', QuotationConvertView.as_view(), name='convert_by_number'),
]
