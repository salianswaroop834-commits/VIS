from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, View, ListView
from django.http import JsonResponse, HttpResponse
from django.db import connection
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone


class HealthCheckView(View):
    """
    Production-grade health check endpoint.
    Verifies backend responsiveness and database connectivity.
    """
    def get(self, request, *args, **kwargs):
        db_ok = True
        db_err = None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as e:
            db_ok = False
            db_err = str(e)

        payload = {
            'status': 'healthy' if db_ok else 'degraded',
            'database': 'connected' if db_ok else f'error: {db_err}',
            'service': 'nexisure-vehicle-insurance',
            'environment': 'development',
        }
        status_code = 200 if db_ok else 503
        return JsonResponse(payload, status=status_code)


class RobotsTxtView(View):
    """
    Implements SEO best practices by excluding private portals
    and admin routes from search crawler indexing.
    """
    def get(self, request, *args, **kwargs):
        lines = [
            "User-agent: *",
            "Disallow: /customer/",
            "Disallow: /staff/",
            "Disallow: /django-admin/",
            "Disallow: /claims/manage/",
            "Disallow: /api/",
            "Allow: /",
            "Sitemap: /sitemap.xml",
        ]
        return HttpResponse("\n".join(lines), content_type="text/plain")


class SitemapView(View):
    """Generates a simple XML sitemap for public-facing pages."""
    def get(self, request, *args, **kwargs):
        base = request.build_absolute_uri('/')[:-1]
        urls = [
            ('/', '1.0', 'weekly'),
            ('/coverage/', '0.9', 'monthly'),
            ('/how-it-works/', '0.8', 'monthly'),
            ('/faq/', '0.8', 'monthly'),
            ('/about/', '0.7', 'monthly'),
            ('/contact/', '0.7', 'monthly'),
            ('/terms/', '0.5', 'yearly'),
            ('/privacy/', '0.5', 'yearly'),
            ('/disclaimer/', '0.5', 'yearly'),
        ]
        today = timezone.now().strftime('%Y-%m-%d')
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for path, priority, freq in urls:
            lines.append(
                f'  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod>'
                f'<changefreq>{freq}</changefreq><priority>{priority}</priority></url>'
            )
        lines.append('</urlset>')
        return HttpResponse('\n'.join(lines), content_type='application/xml')


class HomeView(TemplateView):
    template_name = 'public/home.html'


class AboutView(TemplateView):
    template_name = 'public/about.html'


class CoverageView(TemplateView):
    template_name = 'public/coverage.html'


class HowItWorksView(TemplateView):
    template_name = 'public/how_it_works.html'


class FaqView(TemplateView):
    template_name = 'public/faq.html'


class ContactView(TemplateView):
    template_name = 'public/contact.html'


class TermsView(TemplateView):
    template_name = 'public/terms.html'


class PrivacyView(TemplateView):
    template_name = 'public/privacy.html'


class CookieNoticeView(TemplateView):
    """Cookie and data usage notice for GDPR/privacy transparency."""
    template_name = 'public/cookie_notice.html'


class DisclaimerView(TemplateView):
    """Standalone educational prototype disclaimer page."""
    template_name = 'public/disclaimer.html'


class NotificationsView(LoginRequiredMixin, ListView):
    """
    Displays all in-app notifications for the authenticated user,
    ordered newest first, with read/unread visual distinction.
    """
    template_name = 'core/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        from core.models import Notification
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = self.get_queryset().filter(is_read=False).count()
        return ctx


class NotificationMarkReadView(LoginRequiredMixin, View):
    """AJAX/POST endpoint to mark a notification as read."""

    def post(self, request, pk):
        from core.models import Notification
        from django.shortcuts import get_object_or_404
        notif = get_object_or_404(Notification, id=pk, recipient=request.user)
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        return JsonResponse({'success': True})


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """Marks all unread notifications as read for the authenticated user."""

    def post(self, request):
        from core.models import Notification
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'success': True, 'message': 'All notifications marked as read.'})


# Custom Error Handlers
def custom_page_not_found_view(request, exception):
    return render(request, 'errors/404.html', status=404)


def custom_permission_denied_view(request, exception):
    return render(request, 'errors/403.html', status=403)


def custom_server_error_view(request):
    return render(request, 'errors/500.html', status=500)
