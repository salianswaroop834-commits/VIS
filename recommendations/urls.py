from django.urls import path
from .views import RecommendationListView, RecommendationDetailView

app_name = 'recommendations'

urlpatterns = [
    path('', RecommendationListView.as_view(), name='list'),
    path('<uuid:pk>/', RecommendationDetailView.as_view(), name='detail'),
]
