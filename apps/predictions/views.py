from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from core.permissions import RoleRequiredMixin
from apps.accounts.models import UserRole
from .models import ModelVersion, PredictionLog
from .services.mlops_service import MlopsService
from ml.inference.predictor import InsurancePredictor
from apps.recommendations.services.recommendation_service import RecommendationService
from apps.vehicles.models import VehicleType, FuelType, UsageType
from apps.quotations.models import CoveragePlanCode


class ModelVersionListView(ListView):
    model = ModelVersion
    template_name = 'predictions/model_list.html'
    context_object_name = 'models'

    def get_queryset(self):
        return ModelVersion.objects.all().order_by('-is_active_for_inference', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['governance'] = MlopsService.get_governance_metrics()
        ctx['summary'] = MlopsService.get_registered_models_summary()
        return ctx


class ModelPromoteView(RoleRequiredMixin, View):
    """
    Staff action to promote an approved model version into active inference.
    Deactivates previous active versions for the same model name with audit trail.
    """
    allowed_roles = [UserRole.ADMINISTRATOR, UserRole.UNDERWRITER]

    def post(self, request, pk):
        try:
            model = MlopsService.promote_model(pk, activated_by=request.user)
            messages.success(
                request,
                f"Model '{model.model_name}' v{model.version} promoted to active inference."
            )
        except Exception as e:
            messages.error(request, f"Promotion failed: {str(e)}")
        return redirect('predictions:models')


class LivePredictView(View):
    """
    Interactive underwriting & risk evaluation sandbox.
    Allows testing real-time ML inference on vehicle and driver profiles.
    """
    template_name = 'predictions/live_predict.html'

    def get(self, request):
        return render(request, self.template_name, {
            'vehicle_types': VehicleType.choices,
            'fuel_types': FuelType.choices,
            'usage_types': UsageType.choices,
            'coverage_tiers': CoveragePlanCode.choices,
            'result': None,
        })

    def post(self, request):
        payload = {
            'vehicle_age': int(request.POST.get('vehicle_age', 3)),
            'vehicle_type': request.POST.get('vehicle_type', 'SEDAN'),
            'fuel_type': request.POST.get('fuel_type', 'PETROL'),
            'usage_type': request.POST.get('usage_type', 'PERSONAL'),
            'vehicle_value': float(request.POST.get('vehicle_value', 25000.0)),
            'driver_age': int(request.POST.get('driver_age', 35)),
            'annual_mileage': int(request.POST.get('annual_mileage', 12000)),
            'credit_score_tier': request.POST.get('credit_score_tier', 'GOOD'),
            'previous_claims_count': int(request.POST.get('previous_claims_count', 0)),
            'coverage_tier': request.POST.get('coverage_tier', 'COMPREHENSIVE'),
            'deductible_amount': float(request.POST.get('deductible_amount', 1000.0)),
        }

        # 1. Run ML Risk & Severity Inference
        risk_result = InsurancePredictor.predict_risk(payload, record_log=True)

        # 2. Run Coverage Recommendation Engine
        recommendation = RecommendationService.generate_recommendation(
            vehicle_age=payload['vehicle_age'],
            vehicle_value=payload['vehicle_value'],
            usage_type=payload['usage_type'],
            driver_age=payload['driver_age'],
            annual_mileage=payload['annual_mileage'],
        )

        return render(request, self.template_name, {
            'vehicle_types': VehicleType.choices,
            'fuel_types': FuelType.choices,
            'usage_types': UsageType.choices,
            'coverage_tiers': CoveragePlanCode.choices,
            'input_data': payload,
            'result': risk_result,
            'recommendation': recommendation,
        })


class PredictionLogListView(LoginRequiredMixin, ListView):
    model = PredictionLog
    template_name = 'predictions/prediction_logs.html'
    context_object_name = 'logs'
    paginate_by = 50
