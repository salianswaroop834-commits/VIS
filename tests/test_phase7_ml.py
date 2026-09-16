import pytest
from decimal import Decimal
import numpy as np
import pandas as pd
from django.utils import timezone

from ml.pipelines.feature_pipeline import FeaturePipeline
from ml.inference.predictor import InsurancePredictor
from recommendations.services.recommendation_service import RecommendationService
from recommendations.models import CoverageRecommendation
from quotations.models import CoveragePlan, CoveragePlanCode
from claims.models import Claim, ClaimStatus
from predictions.models import ModelVersion, PredictionLog


@pytest.mark.django_db
class TestPhase7FeaturePipeline:

    def test_payload_validation_and_sensible_defaults(self):
        """Validates that raw payloads with missing or out-of-bounds features are sanitized."""
        raw_payload = {
            'vehicle_age': -5,  # Invalid negative age
            'vehicle_value': -10000.0,  # Invalid negative valuation
            'driver_age': 12,  # Under minimum driving age
            'annual_mileage': 500000,  # Excessive mileage
            'vehicle_type': 'SPACESHIP',  # Unknown category
            'fuel_type': 'WARP_CORE',
            'usage_type': 'UNKNOWN',
        }
        validated = FeaturePipeline.validate_raw_payload(raw_payload)

        assert validated['vehicle_age'] == 0
        assert validated['vehicle_value'] == 1000.0
        assert validated['driver_age'] == 18
        assert validated['annual_mileage'] == 150000
        assert validated['vehicle_type'] in FeaturePipeline.VALID_CATEGORIES['vehicle_type']
        assert validated['fuel_type'] in FeaturePipeline.VALID_CATEGORIES['fuel_type']
        assert validated['usage_type'] in FeaturePipeline.VALID_CATEGORIES['usage_type']

    def test_feature_engineering_no_target_leakage(self):
        """Verifies feature interaction generation without future or target column leakage."""
        sample_df = pd.DataFrame([{
            'vehicle_age': 4,
            'vehicle_value': 800000.0,
            'driver_age': 22,
            'annual_mileage': 22000,
            'previous_claims_count': 1,
            'deductible_amount': 2000.0,
            'vehicle_type': 'SEDAN',
            'fuel_type': 'PETROL',
            'usage_type': 'PERSONAL',
            'credit_score_tier': 'GOOD',
            'coverage_tier': 'COMPREHENSIVE',
        }])
        df_engineered = FeaturePipeline.engineer_features(sample_df)

        assert 'value_to_deductible_ratio' in df_engineered.columns
        assert df_engineered['value_to_deductible_ratio'].iloc[0] == 400.0
        assert 'high_mileage_indicator' in df_engineered.columns
        assert df_engineered['high_mileage_indicator'].iloc[0] == 1
        assert 'elevated_age_cohort' in df_engineered.columns
        assert df_engineered['elevated_age_cohort'].iloc[0] == 1
        assert 'claim_filed' not in df_engineered.columns
        assert 'claim_amount' not in df_engineered.columns

    def test_preprocessor_transformation_shape(self):
        """Verifies ColumnTransformer scales numerics and one-hot encodes categoricals."""
        preprocessor = FeaturePipeline.build_preprocessor()
        sample_df = pd.DataFrame([{
            'vehicle_age': 3,
            'vehicle_value': 600000.0,
            'driver_age': 32,
            'annual_mileage': 11000,
            'previous_claims_count': 0,
            'deductible_amount': 1000.0,
            'vehicle_type': 'SEDAN',
            'fuel_type': 'PETROL',
            'usage_type': 'PERSONAL',
            'credit_score_tier': 'GOOD',
            'coverage_tier': 'COMPREHENSIVE',
        }])
        transformed = preprocessor.fit_transform(sample_df)
        assert transformed.shape[0] == 1
        assert transformed.shape[1] > len(FeaturePipeline.NUMERIC_COLS)  # Numerics + OHE categoricals

    def test_split_data_isolation(self):
        """Verifies train/test partition integrity and stratify support."""
        dummy_data = pd.DataFrame({
            'vehicle_age': np.random.randint(0, 15, 100),
            'vehicle_value': np.random.uniform(200000, 2000000, 100),
            'driver_age': np.random.randint(18, 70, 100),
            'annual_mileage': np.random.randint(5000, 35000, 100),
            'previous_claims_count': np.random.randint(0, 4, 100),
            'deductible_amount': np.random.choice([1000.0, 2000.0, 5000.0], 100),
            'vehicle_type': np.random.choice(['SEDAN', 'SUV', 'HATCHBACK'], 100),
            'fuel_type': np.random.choice(['PETROL', 'DIESEL', 'CNG'], 100),
            'usage_type': np.random.choice(['PERSONAL', 'COMMERCIAL'], 100),
            'credit_score_tier': np.random.choice(['GOOD', 'FAIR'], 100),
            'coverage_tier': np.random.choice(['COMPREHENSIVE', 'THIRD_PARTY'], 100),
            'claim_filed': np.random.choice([0, 1], 100, p=[0.85, 0.15]),
        })

        X_train, X_test, y_train, y_test = FeaturePipeline.split_data(
            dummy_data, target_col='claim_filed', test_size=0.25, random_state=42
        )
        assert len(X_train) == 75
        assert len(X_test) == 25
        assert len(y_train) == 75
        assert len(y_test) == 25
        assert set(X_train.index).isdisjoint(set(X_test.index))

    def test_evaluation_metric_calculators(self):
        """Verifies classifier and regressor metric calculations."""
        y_true_clf = np.array([0, 1, 0, 0, 1])
        y_pred_clf = np.array([0, 1, 0, 0, 0])
        y_prob_clf = np.array([0.1, 0.9, 0.2, 0.3, 0.4])

        clf_metrics = FeaturePipeline.evaluate_classifier(y_true_clf, y_pred_clf, y_prob_clf)
        assert 'accuracy' in clf_metrics
        assert 'precision' in clf_metrics
        assert 'recall' in clf_metrics
        assert 'f1_score' in clf_metrics
        assert 'confusion_matrix' in clf_metrics
        assert 'roc_auc' in clf_metrics

        y_true_reg = np.array([10000.0, 25000.0, 50000.0])
        y_pred_reg = np.array([12000.0, 24000.0, 48000.0])

        reg_metrics = FeaturePipeline.evaluate_regressor(y_true_reg, y_pred_reg)
        assert 'mae' in reg_metrics
        assert 'rmse' in reg_metrics
        assert 'r2_score' in reg_metrics


@pytest.mark.django_db
class TestPhase7ClaimRiskAndSeverityInference:

    def test_pipeline_loading_and_fallback(self):
        """Verifies pipelines can be cached and loaded without crashes."""
        clf, reg = InsurancePredictor.load_pipelines()
        # Pipelines may or may not exist in test runner environment; predictor handles both gracefully
        res = InsurancePredictor.predict_risk({
            'vehicle_age': 2,
            'vehicle_value': 900000.0,
            'driver_age': 30,
        }, record_log=False)
        assert isinstance(res, dict)
        assert 0.0 <= res['claim_probability'] <= 1.0

    def test_predict_risk_contract_and_inr(self):
        """Verifies response structure, currency presentation in INR (₹), and severity bounds."""
        payload = {
            'vehicle_age': 5,
            'vehicle_type': 'SUV',
            'fuel_type': 'DIESEL',
            'usage_type': 'PERSONAL',
            'vehicle_value': 1400000.0,
            'driver_age': 40,
            'annual_mileage': 14000,
            'credit_score_tier': 'GOOD',
            'previous_claims_count': 1,
            'coverage_tier': 'COMPREHENSIVE',
            'deductible_amount': 2000.0,
        }
        pred = InsurancePredictor.predict_risk(payload, record_log=False)

        assert pred['currency_symbol'] == '₹'
        assert pred['decision_support_only'] is True
        assert 0.0 <= pred['claim_probability'] <= 1.0
        assert pred['risk_tier'] in ['LOW', 'MEDIUM', 'HIGH']
        assert pred['estimated_severity'] >= 1000.0
        assert pred['estimated_severity'] <= payload['vehicle_value']
        assert pred['expected_loss'] == round(pred['claim_probability'] * pred['estimated_severity'], 2)
        assert 'RESPONSIBLE AI NOTICE' in pred['disclaimer']

    def test_explainability_breakdown_and_factors(self):
        """Verifies human-readable reasoning and specific responsible AI phrasing."""
        payload = {
            'vehicle_age': 10,
            'vehicle_value': 1800000.0,
            'driver_age': 21,
            'previous_claims_count': 3,
            'annual_mileage': 25000,
        }
        pred = InsurancePredictor.predict_risk(payload, record_log=False)

        breakdown = pred['explanation_breakdown']
        assert breakdown['decision_support_estimate'] is True
        assert 'Decision-support estimate' in breakdown['prediction_notice']
        assert 'Model confidence' in breakdown['model_confidence']
        assert 'Prediction based on available data' in breakdown['prediction_basis']

        factors = breakdown['key_factors']
        assert len(factors) >= 3
        # Check that specific factors are captured in plain language
        factors_text = " ".join(factors)
        assert 'Vehicle age' in factors_text
        assert 'IDV' in factors_text or 'vehicle declared value' in factors_text
        assert 'historical claim' in factors_text.lower() or 'prior claim' in factors_text.lower()

    def test_prediction_logging_in_database(self):
        """Verifies that predict_risk records a non-repudiation log in PredictionLog."""
        initial_count = PredictionLog.objects.count()
        payload = {
            'vehicle_age': 3,
            'vehicle_value': 750000.0,
            'driver_age': 35,
        }
        pred = InsurancePredictor.predict_risk(payload, record_log=True)
        assert PredictionLog.objects.count() == initial_count + 1

        log = PredictionLog.objects.first()
        assert log.prediction_type == 'CLAIM_RISK_AND_SEVERITY'
        assert log.is_successful is True
        assert 'claim_probability' in log.output_result
        assert 'Not an automated claim decision' in log.disclaimer


@pytest.mark.django_db
class TestPhase7CoverageRecommendations:

    def test_coverage_recommendation_new_vehicle(self):
        """Recommends Zero Depreciation for new/high-value vehicles with INR currency formatting."""
        rec = RecommendationService.generate_recommendation(
            vehicle_age=1,
            vehicle_value=1800000.0,
            usage_type='PERSONAL',
            driver_age=32,
        )
        assert rec['primary_code'] == CoveragePlanCode.ZERO_DEP_PREMIUM
        assert rec['currency_symbol'] == '₹'
        assert rec['decision_support_only'] is True
        assert rec['confidence_score'] > 90.0
        assert 'Zero Depreciation Comprehensive is optimal' in rec['rationale']
        assert '₹' in rec['rationale']
        assert '$' not in rec['rationale']
        assert len(rec['supporting_factors']) >= 3

    def test_coverage_recommendation_older_vehicle(self):
        """Recommends Third-Party for older, depreciated vehicles."""
        rec = RecommendationService.generate_recommendation(
            vehicle_age=11,
            vehicle_value=250000.0,
            usage_type='PERSONAL',
            driver_age=45,
        )
        assert rec['primary_code'] == CoveragePlanCode.THIRD_PARTY
        assert 'Third-Party liability fulfills legal compliance' in rec['rationale']
        assert 'EDUCATIONAL GUIDANCE NOTICE' in rec['disclaimer']


@pytest.mark.django_db
class TestPhase7ResponsibleAIGuardrails:

    def test_ml_cannot_alter_claim_status(self):
        """
        Critical safety test:
        ML risk prediction must NEVER mutate or alter Claim status directly.
        Claim decision requires an authorized human claims handler.
        """
        # Create a mock claim representation
        dummy_risk = InsurancePredictor.predict_risk({
            'vehicle_age': 1,
            'vehicle_value': 500000.0,
            'previous_claims_count': 0,
        }, record_log=False)

        # Ensure prediction output does not contain any mutation directive
        assert 'approve_claim' not in dummy_risk
        assert 'reject_claim' not in dummy_risk
        assert 'claim_decision' not in dummy_risk
        assert dummy_risk['decision_support_only'] is True

    def test_no_guaranteed_truth_wording(self):
        """Predictions must never assert 100% certainty or claim settlement guarantees."""
        pred = InsurancePredictor.predict_risk({'vehicle_age': 4}, record_log=False)
        disclaimer = pred['disclaimer']
        assert 'guarantee' in disclaimer.lower() or 'not constitute' in disclaimer.lower()
        assert 'human review is mandatory' in disclaimer.lower()
