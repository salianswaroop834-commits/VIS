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
    CookieNoticeView,
    DisclaimerView,
    SitemapView,
    NotificationsView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
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
    path('cookie-notice/', CookieNoticeView.as_view(), name='cookie-notice'),
    path('disclaimer/', DisclaimerView.as_view(), name='disclaimer'),
    path('sitemap.xml', SitemapView.as_view(), name='sitemap'),

    # Notifications
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('notifications/<uuid:pk>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
]

