"""
Root URL Configuration for Nexisure Vehicle Insurance Platform.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from core.views import HealthCheckView, RobotsTxtView

urlpatterns = [
    # Built-in Django Admin (Staff back-office)
    path('django-admin/', admin.site.urls),
    path('admin/', RedirectView.as_view(url='/django-admin/', permanent=False)),

    # Health Check & Search Engine Directives
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('api/health/', RedirectView.as_view(url='/health/', permanent=False)),
    path('robots.txt', RobotsTxtView.as_view(), name='robots-txt'),
    path('robots.txt/', RedirectView.as_view(url='/robots.txt', permanent=False)),
    path('plans/', RedirectView.as_view(url='/coverage/', permanent=False)),
    path('staff/dashboard/', RedirectView.as_view(url='/staff/underwriter/dashboard/', permanent=False)),

    # Public marketing & informational website
    path('', include('core.urls')),

    # Authentication (Email OTP, Login, Logout, Session)
    path('auth/', include('apps.accounts.urls')),

    # Customer Portal
    path('customer/', include('apps.customers.urls')),

    # Staff Portals (Underwriter, Claims Handler, Administrator)
    path('staff/', include('apps.staff.urls')),

    # Core Insurance Lifecycle Domains
    path('vehicles/', include('apps.vehicles.urls')),
    path('quotations/', include('apps.quotations.urls')),
    path('policies/', include('apps.policies.urls')),
    path('claims/', include('apps.claims.urls')),
    path('services/', include('apps.service_requests.urls')),
    path('payments/', include('apps.payments.urls')),

    # AI, RAG & Decision-Support Services
    path('predictions/', include('apps.predictions.urls')),
    path('rag/', include('apps.rag.urls')),
    path('chatbot/', include('apps.chatbot.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('audit/', include('apps.audit.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
