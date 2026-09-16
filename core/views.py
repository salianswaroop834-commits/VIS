from django.shortcuts import render
from django.views.generic import TemplateView, View
from django.http import JsonResponse, HttpResponse
from django.db import connection


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


# Custom Error Handlers
def custom_page_not_found_view(request, exception):
    return render(request, 'errors/404.html', status=404)


def custom_permission_denied_view(request, exception):
    return render(request, 'errors/403.html', status=403)


def custom_server_error_view(request):
    return render(request, 'errors/500.html', status=500)
