from django.urls import path
from .views import (
    KnowledgeBaseListView,
    KnowledgeBaseDetailView,
    RagSearchView,
    RagIngestView,
    UnsafeRagDemoView,
)

app_name = 'rag'

urlpatterns = [
    path('search/', RagSearchView.as_view(), name='search'),
    path('unsafe-demo/', UnsafeRagDemoView.as_view(), name='unsafe-demo'),
    path('docs/', KnowledgeBaseListView.as_view(), name='list'),
    path('docs/ingest/', RagIngestView.as_view(), name='ingest'),
    path('docs/<uuid:pk>/', KnowledgeBaseDetailView.as_view(), name='detail'),
]

