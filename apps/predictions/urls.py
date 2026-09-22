from django.urls import path
from .views import (
    ModelVersionListView,
    ModelPromoteView,
    PredictionLogListView,
    LivePredictView,
)

app_name = 'predictions'

urlpatterns = [
    path('models/', ModelVersionListView.as_view(), name='models'),
    path('models/<uuid:pk>/promote/', ModelPromoteView.as_view(), name='promote'),
    path('predict/', LivePredictView.as_view(), name='live-predict'),
    path('logs/', PredictionLogListView.as_view(), name='logs'),
]
