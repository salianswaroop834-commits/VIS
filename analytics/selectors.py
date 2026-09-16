from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date, datetime
from django.db.models import Count, Sum, Avg, Min, Max, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from policies.models import Policy, PolicyStatus
from quotations.models import CoveragePlan, QuotationDraft
from customers.models import CustomerProfile
from vehicles.models import Vehicle, VehicleType, FuelType
from claims.models import Claim, ClaimStatus
from service_requests.models import ServiceRequest, ServiceRequestStatus, ServiceRequestType


def _apply_policy_filters(
    qs,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    plan_code: Optional[str] = None,
):
    if start_date:
        qs = qs.filter(start_date__gte=start_date)
    if end_date:
        qs = qs.filter(start_date__lte=end_date)
    if status and status in PolicyStatus.values:
        qs = qs.filter(status=status)
    if plan_code:
        qs = qs.filter(coverage_plan__plan_code=plan_code)
    return qs


def get_policy_portfolio_metrics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    plan_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes comprehensive database-backed policy portfolio metrics.
    Gracefully handles empty databases with zero-values.
    """
    qs = _apply_policy_filters(Policy.objects.all(), start_date, end_date, status, plan_code)
    total_count = qs.count()

    # Aggregate counts by status
    status_counts = qs.aggregate(
        active=Count('id', filter=Q(status=PolicyStatus.ACTIVE)),
        expired=Count('id', filter=Q(status=PolicyStatus.EXPIRED)),
        cancelled=Count('id', filter=Q(status=PolicyStatus.CANCELLED)),
        renewed=Count('id', filter=Q(status=PolicyStatus.RENEWED)),
    )

    # Financial aggregations
    financials = qs.aggregate(
        total_premium=Sum('premium_amount'),
        avg_premium=Avg('premium_amount'),
        avg_deductible=Avg('deductible_amount'),
        avg_idv=Avg('vehicle__vehicle_value'),
    )

    # Term distribution
    term_counts = qs.values('duration_years').annotate(count=Count('id')).order_by('duration_years')
    term_dist = {item['duration_years']: item['count'] for item in term_counts}

    total_premium = financials['total_premium'] or Decimal('0.00')
    avg_premium = financials['avg_premium'] or Decimal('0.00')
    avg_deductible = financials['avg_deductible'] or Decimal('0.00')
    avg_idv = financials['avg_idv'] or Decimal('0.00')

    return {
        'total_policies': total_count,
        'active_policies': status_counts['active'] or 0,
        'expired_policies': status_counts['expired'] or 0,
        'cancelled_policies': status_counts['cancelled'] or 0,
        'renewed_policies': status_counts['renewed'] or 0,
        'total_premium': total_premium,
        'avg_premium': round(avg_premium, 2),
        'avg_deductible': round(avg_deductible, 2),
        'avg_idv': round(avg_idv, 2),
        'term_distribution': term_dist,
    }


def get_policy_status_distribution(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Returns distribution of policies across statuses with counts and percentages."""
    qs = _apply_policy_filters(Policy.objects.all(), start_date, end_date)
    total = qs.count()

    raw = qs.values('status').annotate(count=Count('id')).order_by('-count')
    result = []
    for item in raw:
        cnt = item['count']
        pct = round((cnt / total * 100.0), 2) if total > 0 else 0.0
        result.append({
            'status': item['status'],
            'count': cnt,
            'percentage': pct,
        })
    return result


def get_policy_plan_distribution(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Returns policy counts and premium volumes partitioned by coverage plan."""
    qs = _apply_policy_filters(Policy.objects.all(), start_date, end_date)
    total = qs.count()

    raw = qs.values(
        'coverage_plan__plan_code',
        'coverage_plan__name',
    ).annotate(
        count=Count('id'),
        premium_sum=Sum('premium_amount'),
    ).order_by('-count')

    result = []
    for item in raw:
        cnt = item['count']
        pct = round((cnt / total * 100.0), 2) if total > 0 else 0.0
        prem = item['premium_sum'] or Decimal('0.00')
        result.append({
            'plan_code': item['coverage_plan__plan_code'],
            'plan_name': item['coverage_plan__name'],
            'count': cnt,
            'percentage': pct,
            'total_premium': prem,
        })
    return result


def get_policy_time_series(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Monthly policy volume and premium aggregation using TruncMonth."""
    qs = _apply_policy_filters(Policy.objects.all(), start_date, end_date)
    raw = (
        qs.annotate(month=TruncMonth('start_date'))
        .values('month')
        .annotate(
            policy_count=Count('id'),
            total_premium=Sum('premium_amount'),
        )
        .order_by('month')
    )

    result = []
    for item in raw:
        if item['month']:
            m_str = item['month'].strftime('%Y-%m')
            result.append({
                'month': m_str,
                'policy_count': item['policy_count'],
                'total_premium': item['total_premium'] or Decimal('0.00'),
            })
    return result


def get_customer_portfolio_metrics() -> Dict[str, Any]:
    """Computes customer portfolio metrics, active policy holders, and distribution."""
    total_customers = CustomerProfile.objects.count()
    active_customers = (
        CustomerProfile.objects.filter(policies__status=PolicyStatus.ACTIVE)
        .distinct()
        .count()
    )

    total_active_policies = Policy.objects.filter(status=PolicyStatus.ACTIVE).count()
    policies_per_customer = (
        round(total_active_policies / active_customers, 2) if active_customers > 0 else 0.0
    )

    # Geographic distribution by state
    geo_raw = (
        CustomerProfile.objects.exclude(state='')
        .values('state')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    geo_dist = {item['state']: item['count'] for item in geo_raw}

    return {
        'total_customers': total_customers,
        'customers_with_active_policies': active_customers,
        'policies_per_customer': policies_per_customer,
        'geographic_distribution': geo_dist,
    }


def get_vehicle_portfolio_metrics() -> Dict[str, Any]:
    """Computes vehicle fleet metrics, fuel type, category breakdown, and IDV stats."""
    qs = Vehicle.objects.all()
    total_vehicles = qs.count()
    active_vehicles = qs.filter(policies__status=PolicyStatus.ACTIVE).distinct().count()
    inactive_vehicles = max(0, total_vehicles - active_vehicles)

    fuel_counts = qs.values('fuel_type').annotate(count=Count('id')).order_by('-count')
    fuel_dist = {item['fuel_type']: item['count'] for item in fuel_counts}

    type_counts = qs.values('vehicle_type').annotate(count=Count('id')).order_by('-count')
    type_dist = {item['vehicle_type']: item['count'] for item in type_counts}

    idv_stats = qs.aggregate(
        avg_idv=Avg('vehicle_value'),
        min_idv=Min('vehicle_value'),
        max_idv=Max('vehicle_value'),
    )

    return {
        'total_vehicles': total_vehicles,
        'active_vehicles': active_vehicles,
        'inactive_vehicles': inactive_vehicles,
        'fuel_type_distribution': fuel_dist,
        'vehicle_type_distribution': type_dist,
        'avg_idv': round(idv_stats['avg_idv'] or Decimal('0.00'), 2),
        'min_idv': idv_stats['min_idv'] or Decimal('0.00'),
        'max_idv': idv_stats['max_idv'] or Decimal('0.00'),
    }


def get_claim_portfolio_metrics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Computes claims portfolio statistics, status breakdown, loss and settlement totals."""
    qs = Claim.objects.all()
    if start_date:
        qs = qs.filter(incident_date__date__gte=start_date)
    if end_date:
        qs = qs.filter(incident_date__date__lte=end_date)
    if status and status in ClaimStatus.values:
        qs = qs.filter(status=status)

    total_claims = qs.count()

    status_counts = qs.aggregate(
        pending=Count('id', filter=Q(status=ClaimStatus.PENDING)),
        in_review=Count('id', filter=Q(status=ClaimStatus.IN_REVIEW)),
        approved=Count('id', filter=Q(status=ClaimStatus.APPROVED)),
        rejected=Count('id', filter=Q(status=ClaimStatus.REJECTED)),
        settled=Count('id', filter=Q(status=ClaimStatus.SETTLED)),
    )

    loss_stats = qs.aggregate(
        total_estimated_loss=Sum('estimated_loss_amount'),
        avg_estimated_loss=Avg('estimated_loss_amount'),
        total_settlement_authorized=Sum('settlement_amount'),
        avg_settlement=Avg('settlement_amount'),
    )

    # Claim frequency relative to active policies
    active_policies = Policy.objects.filter(status=PolicyStatus.ACTIVE).count()
    claim_frequency_pct = (
        round((total_claims / active_policies * 100.0), 2) if active_policies > 0 else 0.0
    )

    total_est_loss = loss_stats['total_estimated_loss'] or Decimal('0.00')
    total_settled_auth = loss_stats['total_settlement_authorized'] or Decimal('0.00')

    return {
        'total_claims': total_claims,
        'pending_claims': status_counts['pending'] or 0,
        'in_review_claims': status_counts['in_review'] or 0,
        'approved_claims': status_counts['approved'] or 0,
        'rejected_claims': status_counts['rejected'] or 0,
        'settled_claims': status_counts['settled'] or 0,
        'claim_frequency_pct': claim_frequency_pct,
        'total_estimated_loss': total_est_loss,
        'total_settlement_authorized': total_settled_auth,
        'avg_estimated_loss': round(loss_stats['avg_estimated_loss'] or Decimal('0.00'), 2),
        'avg_settlement': round(loss_stats['avg_settlement'] or Decimal('0.00'), 2),
    }


def get_claim_status_distribution() -> List[Dict[str, Any]]:
    """Returns claims counts and percentages partitioned by ClaimStatus."""
    qs = Claim.objects.all()
    total = qs.count()
    raw = qs.values('status').annotate(count=Count('id')).order_by('-count')

    result = []
    for item in raw:
        cnt = item['count']
        pct = round((cnt / total * 100.0), 2) if total > 0 else 0.0
        result.append({
            'status': item['status'],
            'count': cnt,
            'percentage': pct,
        })
    return result


def get_claim_time_series() -> List[Dict[str, Any]]:
    """Monthly claim filing volume and authorized settlement amounts."""
    raw = (
        Claim.objects.annotate(month=TruncMonth('incident_date'))
        .values('month')
        .annotate(
            claim_count=Count('id'),
            total_loss=Sum('estimated_loss_amount'),
            total_settlement=Sum('settlement_amount'),
        )
        .order_by('month')
    )

    result = []
    for item in raw:
        if item['month']:
            m_str = item['month'].strftime('%Y-%m')
            result.append({
                'month': m_str,
                'claim_count': item['claim_count'],
                'total_loss': item['total_loss'] or Decimal('0.00'),
                'total_settlement': item['total_settlement'] or Decimal('0.00'),
            })
    return result


def get_service_request_metrics() -> Dict[str, Any]:
    """Computes service request volume, type breakdown, and resolution status counts."""
    qs = ServiceRequest.objects.all()
    total = qs.count()

    by_type_raw = qs.values('request_type').annotate(count=Count('id')).order_by('-count')
    by_type = {item['request_type']: item['count'] for item in by_type_raw}

    by_status_raw = qs.values('status').annotate(count=Count('id')).order_by('-count')
    by_status = {item['status']: item['count'] for item in by_status_raw}

    return {
        'total_requests': total,
        'requests_by_type': by_type,
        'requests_by_status': by_status,
    }


def get_financial_portfolio_metrics() -> Dict[str, Any]:
    """
    Computes top-level financial portfolio telemetry:
    Gross Premium Written, Incurred Claims, Net Loss Ratio, Total IDV Exposure.
    """
    active_policies = Policy.objects.filter(status=PolicyStatus.ACTIVE)
    gross_premium = active_policies.aggregate(Sum('premium_amount'))['premium_amount__sum'] or Decimal('0.00')
    total_exposure = active_policies.aggregate(Sum('vehicle__vehicle_value'))['vehicle__vehicle_value__sum'] or Decimal('0.00')

    settled_claims = Claim.objects.filter(status__in=[ClaimStatus.APPROVED, ClaimStatus.SETTLED])
    incurred_settlements = settled_claims.aggregate(Sum('settlement_amount'))['settlement_amount__sum'] or Decimal('0.00')

    loss_ratio_pct = (
        round(float((incurred_settlements / gross_premium) * Decimal('100.0')), 2) if gross_premium > 0 else 0.0
    )

    return {
        'gross_premium_written': gross_premium,
        'total_exposure_idv': total_exposure,
        'incurred_settlements': incurred_settlements,
        'loss_ratio_pct': loss_ratio_pct,
    }
