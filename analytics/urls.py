from django.urls import path
from .views import (
     AnalyticsDashboardView,
     LivePortfolioApiView,
     DatasetRecordsApiView,
     DownloadCuratedDatasetCsvView,
 )

app_name = 'analytics'

urlpatterns = [
     path('', AnalyticsDashboardView.as_view(), name='dashboard'),
     path('api/portfolio/', LivePortfolioApiView.as_view(), name='api-portfolio'),
     path('api/records/', DatasetRecordsApiView.as_view(), name='api-records'),
     path('download-csv/', DownloadCuratedDatasetCsvView.as_view(), name='download-csv'),
]
