import pytest
from decimal import Decimal
from django.urls import reverse
from ml.inference.predictor import InsurancePredictor
from apps.recommendations.services.recommendation_service import RecommendationService
from apps.predictions.models import ModelVersion, PredictionLog
from apps.quotations.models import CoveragePlanCode


@pytest.mark.django_db
class TestPhase7MachineLearningAndInference:

    def test_predictor_produces_bounded_probabilities_and_severity(self):
        payload = {
            'vehicle_age': 2,
            'vehicle_type': 'SUV',
            'fuel_type': 'PETROL',
            'usage_type': 'PERSONAL',
            'vehicle_value': 35000.0,
            'driver_age': 32,
            'annual_mileage': 11000,
            'credit_score_tier': 'GOOD',
            'previous_claims_count': 0,
            'coverage_tier': 'COMPREHENSIVE',
            'deductible_amount': 1000.0,
        }

        result = InsurancePredictor.predict_risk(payload, record_log=False)

        assert 'claim_probability' in result
        assert 0.0 <= result['claim_probability'] <= 1.0

        assert result['risk_tier'] in ('LOW', 'MEDIUM', 'HIGH')
        assert 150.0 <= result['estimated_severity'] <= payload['vehicle_value']

        # Expected loss verification
        expected = round(result['claim_probability'] * result['estimated_severity'], 2)
        assert abs(result['expected_loss'] - expected) <= 0.05

        # Responsible AI disclaimer
        assert 'RESPONSIBLE AI NOTICE' in result['disclaimer']

    def test_predictor_high_risk_commercial_scenario(self):
        high_risk_payload = {
            'vehicle_age': 1,
            'vehicle_type': 'COMMERCIAL_VAN',
            'fuel_type': 'DIESEL',
            'usage_type': 'COMMERCIAL',
            'vehicle_value': 45000.0,
            'driver_age': 21,
            'annual_mileage': 32000,
            'credit_score_tier': 'POOR',
            'previous_claims_count': 3,
            'coverage_tier': 'COMPREHENSIVE',
            'deductible_amount': 1000.0,
        }

        result = InsurancePredictor.predict_risk(high_risk_payload, record_log=False)
        assert result['claim_probability'] > 0.15
        assert result['risk_tier'] in ('MEDIUM', 'HIGH')
        assert result['recommended_deductible'] >= 1000.0

    def test_coverage_recommendation_logic(self):
        # Scenario A: New luxury car -> Zero Dep recommended
        rec_new = RecommendationService.generate_recommendation(
            vehicle_age=1,
            vehicle_value=45000.0,
            usage_type='PERSONAL',
            driver_age=35,
        )
        assert rec_new['primary_code'] == CoveragePlanCode.ZERO_DEP_PREMIUM
        assert rec_new['confidence_score'] >= 90.0
        assert 'Zero Depreciation' in rec_new['rationale']

        # Scenario B: Older economy car -> Third Party recommended
        rec_old = RecommendationService.generate_recommendation(
            vehicle_age=10,
            vehicle_value=4500.0,
            usage_type='PERSONAL',
            driver_age=50,
        )
        assert rec_old['primary_code'] == CoveragePlanCode.THIRD_PARTY
        assert 'Third-Party' in rec_old['rationale']

    def test_predictions_models_view_renders_registered_models(self, client):
        ModelVersion.objects.create(
            model_name='ClaimProbabilityPredictor',
            version='v1.0.0',
            algorithm_name='RandomForestClassifier',
            artifact_path='ml/artifacts/claim_probability_pipeline.joblib',
            evaluation_metrics={'roc_auc': 0.6145},
            is_active_for_inference=True
        )
        url = reverse('predictions:models')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Deployed Machine Learning Models' in content
        assert 'ClaimProbabilityPredictor' in content or 'RandomForestClassifier' in content

    def test_live_predict_view_get_and_post(self, client):
        url = reverse('predictions:live-predict')

        # GET form
        resp_get = client.get(url)
        assert resp_get.status_code == 200
        assert 'Live Risk & Claim Severity Predictor' in resp_get.content.decode('utf-8')

        # POST submission
        post_data = {
            'vehicle_age': '3',
            'vehicle_type': 'SEDAN',
            'fuel_type': 'PETROL',
            'usage_type': 'PERSONAL',
            'vehicle_value': '28000',
            'driver_age': '30',
            'annual_mileage': '12000',
            'credit_score_tier': 'GOOD',
            'previous_claims_count': '0',
            'coverage_tier': 'COMPREHENSIVE',
            'deductible_amount': '1000',
        }
        resp_post = client.post(url, data=post_data)
        assert resp_post.status_code == 200
        content = resp_post.content.decode('utf-8')
        assert 'ML Risk Evaluation Output' in content
        assert 'Predicted Claim Probability' in content
        assert 'Estimated Severity' in content
        assert 'Recommended Plan' in content
        assert 'RESPONSIBLE AI NOTICE' in content

        # Verify PredictionLog in database
        log_count = PredictionLog.objects.count()
        assert log_count >= 1
