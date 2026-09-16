from django.urls import path
from .views import (
    HomeView,
    AboutView,
    CoverageView,
    HowItWorksView,
    FaqView,
    ContactView,
    TermsView,
    PrivacyView,
)

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('about/', AboutView.as_view(), name='about'),
    path('coverage/', CoverageView.as_view(), name='coverage'),
    path('how-it-works/', HowItWorksView.as_view(), name='how-it-works'),
    path('faq/', FaqView.as_view(), name='faq'),
    path('contact/', ContactView.as_view(), name='contact'),
    path('terms/', TermsView.as_view(), name='terms'),
    path('privacy/', PrivacyView.as_view(), name='privacy'),
]
