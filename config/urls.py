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
    path('robots.txt', RobotsTxtView.as_view(), name='robots-txt'),

    # Public marketing & informational website
    path('', include('core.urls')),

    # Authentication (Email OTP, Login, Logout, Session)
    path('auth/', include('accounts.urls')),

    # Customer Portal
    path('customer/', include('customers.urls')),

    # Staff Portals (Underwriter, Claims Handler, Administrator)
    path('staff/', include('staff.urls')),

    # Core Insurance Lifecycle Domains
    path('vehicles/', include('vehicles.urls')),
    path('quotations/', include('quotations.urls')),
    path('policies/', include('policies.urls')),
    path('claims/', include('claims.urls')),
    path('services/', include('service_requests.urls')),
    path('payments/', include('payments.urls')),

    # AI, RAG & Decision-Support Services
    path('predictions/', include('predictions.urls')),
    path('rag/', include('rag.urls')),
    path('chatbot/', include('chatbot.urls')),
    path('analytics/', include('analytics.urls')),
    path('audit/', include('audit.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
