from django.views.generic import ListView, DetailView
from .models import CoverageRecommendation


class RecommendationListView(ListView):
    model = CoverageRecommendation
    template_name = 'recommendations/recommendation_list.html'
    context_object_name = 'recommendations'


class RecommendationDetailView(DetailView):
    model = CoverageRecommendation
    template_name = 'recommendations/recommendation_detail.html'
    context_object_name = 'recommendation'
