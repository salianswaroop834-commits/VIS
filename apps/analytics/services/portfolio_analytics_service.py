from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from django.utils.dateparse import parse_date

from apps.analytics import selectors


class PortfolioAnalyticsService:
    """
    High-level orchestration service for database-backed portfolio analytics.
    Exposes clean APIs for dashboard views, JSON endpoints, and future feature pipelines.
    Formats all currency values in INR (₹).
    """

    @classmethod
    def parse_filters(cls, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not params:
            return {}

        parsed = {}
        start_raw = params.get('start_date')
        if start_raw:
            parsed['start_date'] = parse_date(str(start_raw)) if isinstance(start_raw, str) else start_raw

        end_raw = params.get('end_date')
        if end_raw:
            parsed['end_date'] = parse_date(str(end_raw)) if isinstance(end_raw, str) else end_raw

        status = params.get('status')
        if status:
            parsed['status'] = str(status).strip()

        plan_code = params.get('plan_code') or params.get('coverage_plan')
        if plan_code:
            parsed['plan_code'] = str(plan_code).strip()

        return parsed

    @classmethod
    def get_policy_portfolio_metrics(cls, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        f = cls.parse_filters(filters)
        return selectors.get_policy_portfolio_metrics(
            start_date=f.get('start_date'),
            end_date=f.get('end_date'),
            status=f.get('status'),
            plan_code=f.get('plan_code'),
        )

    @classmethod
    def get_policy_status_distribution(cls, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        f = cls.parse_filters(filters)
        return selectors.get_policy_status_distribution(
            start_date=f.get('start_date'),
            end_date=f.get('end_date'),
        )

    @classmethod
    def get_policy_plan_distribution(cls, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        f = cls.parse_filters(filters)
        return selectors.get_policy_plan_distribution(
            start_date=f.get('start_date'),
            end_date=f.get('end_date'),
        )

    @classmethod
    def get_policy_time_series(cls, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        f = cls.parse_filters(filters)
        return selectors.get_policy_time_series(
            start_date=f.get('start_date'),
            end_date=f.get('end_date'),
        )

    @classmethod
    def get_customer_portfolio_metrics(cls) -> Dict[str, Any]:
        return selectors.get_customer_portfolio_metrics()

    @classmethod
    def get_vehicle_portfolio_metrics(cls) -> Dict[str, Any]:
        return selectors.get_vehicle_portfolio_metrics()

    @classmethod
    def get_claim_portfolio_metrics(cls, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        f = cls.parse_filters(filters)
        return selectors.get_claim_portfolio_metrics(
            start_date=f.get('start_date'),
            end_date=f.get('end_date'),
            status=f.get('status'),
        )

    @classmethod
    def get_claim_status_distribution(cls) -> List[Dict[str, Any]]:
        return selectors.get_claim_status_distribution()

    @classmethod
    def get_claim_time_series(cls) -> List[Dict[str, Any]]:
        return selectors.get_claim_time_series()

    @classmethod
    def get_service_request_metrics(cls) -> Dict[str, Any]:
        return selectors.get_service_request_metrics()

    @classmethod
    def get_financial_portfolio_metrics(cls) -> Dict[str, Any]:
        return selectors.get_financial_portfolio_metrics()

    @classmethod
    def get_live_portfolio_summary(cls, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Aggregates complete live database-backed portfolio telemetry
        with formatted INR (₹) amounts for dashboard presentation.
        """
        f = cls.parse_filters(filters)

        policy_metrics = cls.get_policy_portfolio_metrics(f)
        customer_metrics = cls.get_customer_portfolio_metrics()
        vehicle_metrics = cls.get_vehicle_portfolio_metrics()
        claim_metrics = cls.get_claim_portfolio_metrics(f)
        financial_metrics = cls.get_financial_portfolio_metrics()
        service_metrics = cls.get_service_request_metrics()

        plan_dist = cls.get_policy_plan_distribution(f)
        status_dist = cls.get_policy_status_distribution(f)
        claim_dist = cls.get_claim_status_distribution()
        policy_trend = cls.get_policy_time_series(f)

        return {
            'currency_symbol': '₹',
            'has_live_data': policy_metrics['total_policies'] > 0 or customer_metrics['total_customers'] > 0,
            'kpis': {
                'active_policies': policy_metrics['active_policies'],
                'total_policies': policy_metrics['total_policies'],
                'total_customers': customer_metrics['total_customers'],
                'active_customers': customer_metrics['customers_with_active_policies'],
                'total_vehicles': vehicle_metrics['total_vehicles'],
                'active_vehicles': vehicle_metrics['active_vehicles'],
                'total_claims': claim_metrics['total_claims'],
                'pending_claims': claim_metrics['pending_claims'],
                'approved_claims': claim_metrics['approved_claims'],
                'settled_claims': claim_metrics['settled_claims'],
                'claim_frequency_pct': claim_metrics['claim_frequency_pct'],
                'total_premium': policy_metrics['total_premium'],
                'avg_premium': policy_metrics['avg_premium'],
                'gross_premium_written': financial_metrics['gross_premium_written'],
                'total_exposure_idv': financial_metrics['total_exposure_idv'],
                'incurred_settlements': financial_metrics['incurred_settlements'],
                'loss_ratio_pct': financial_metrics['loss_ratio_pct'],
                'total_service_requests': service_metrics['total_requests'],
            },
            'distributions': {
                'plans': plan_dist,
                'policy_statuses': status_dist,
                'claim_statuses': claim_dist,
                'vehicle_types': vehicle_metrics['vehicle_type_distribution'],
                'fuel_types': vehicle_metrics['fuel_type_distribution'],
                'service_request_types': service_metrics['requests_by_type'],
                'service_request_statuses': service_metrics['requests_by_status'],
            },
            'time_series': {
                'policy_volume': policy_trend,
                'claim_volume': cls.get_claim_time_series(),
            },
            'applied_filters': f,
        }
