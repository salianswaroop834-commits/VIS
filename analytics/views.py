import csv
from django.views.generic import TemplateView, View
from django.http import JsonResponse, FileResponse, Http404
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from analytics.services.eda_service import EdaService
from analytics.services.portfolio_analytics_service import PortfolioAnalyticsService


class AnalyticsDashboardView(TemplateView):
    template_name = 'analytics/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        # RBAC: Authenticated customers are strictly forbidden from portfolio analytics.
        # Anonymous visitors are allowed for educational/demo EDA baseline backwards-compatibility.
        if request.user.is_authenticated and getattr(request.user, 'is_customer', False):
            raise PermissionDenied("Customers are not authorized to view portfolio analytics.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Load historical/synthetic EDA payload for backward compatibility & chart generation
        payload = EdaService.get_dashboard_payload()
        context.update(payload)

        # Load live database-backed portfolio analytics
        filters = {
            'start_date': self.request.GET.get('start_date'),
            'end_date': self.request.GET.get('end_date'),
            'status': self.request.GET.get('status'),
            'plan_code': self.request.GET.get('plan_code'),
        }
        live_portfolio = PortfolioAnalyticsService.get_live_portfolio_summary(filters=filters)
        context['live_portfolio'] = live_portfolio
        context['applied_filters'] = filters
        return context


class LivePortfolioApiView(View):
    """
    JSON API providing live database-backed portfolio metrics.
    Protected by RBAC:
    - Unauthenticated: 401 Unauthorized
    - Customer: 403 Forbidden
    - Staff / Underwriter / Claims Handler / Administrator: 200 OK
    """
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        if getattr(request.user, 'is_customer', False):
            return JsonResponse({'error': 'Forbidden. Customers cannot access portfolio telemetry.'}, status=403)

        filters = {
            'start_date': request.GET.get('start_date'),
            'end_date': request.GET.get('end_date'),
            'status': request.GET.get('status'),
            'plan_code': request.GET.get('plan_code'),
        }
        data = PortfolioAnalyticsService.get_live_portfolio_summary(filters=filters)
        return JsonResponse(data, encoder=DjangoJSONEncoder)


class DatasetRecordsApiView(View):
    """
    JSON API providing search, filter, and pagination for all authentic CSV records.
    """
    def get(self, request, *args, **kwargs):
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 15))
        search = request.GET.get('search', '').strip()
        filter_type = request.GET.get('filter', 'all').strip()

        data = EdaService.get_authentic_records(
            page=page,
            page_size=page_size,
            search=search,
            filter_type=filter_type,
        )
        return JsonResponse(data)


class DownloadCuratedDatasetCsvView(View):
    """
    Direct download endpoint for the authentic curated dataset CSV.
    """
    def get(self, request, *args, **kwargs):
        path = EdaService.get_curated_path()
        if not path.exists():
            path = EdaService.get_synthetic_path()
        if not path.exists():
            raise Http404("Curated dataset file not found.")

        response = FileResponse(
            open(path, 'rb'),
            as_attachment=True,
            filename='curated_vehicle_insurance_dataset.csv'
        )
        return response

