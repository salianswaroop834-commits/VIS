import pytest
import os
from pathlib import Path
from django.urls import reverse
from accounts.models import User, UserRole
from predictions.models import ModelVersion, PredictionLog
from predictions.services.mlops_service import MlopsService
from audit.models import AuditLog


@pytest.mark.django_db
class TestPhase8MLOpsAndModelRegistry:
    """
    Test suite verifying Phase 8 MLOps, model registry, active version promotion,
    and governance telemetry tracking.
    """

    @pytest.fixture
    def admin_user(self):
        return User.objects.create_user(
            username='admin_mlops',
            email='admin_mlops@nexisure.test',
            first_name='Admin',
            last_name='MLOps',
            role=UserRole.ADMINISTRATOR,
            is_staff=True,
        )

    @pytest.fixture
    def customer_user(self):
        return User.objects.create_user(
            username='customer_mlops',
            email='customer_mlops@nexisure.test',
            first_name='John',
            last_name='Doe',
            role=UserRole.CUSTOMER,
        )

    @pytest.fixture
    def existing_pipeline_file(self, tmp_path):
        dummy_file = tmp_path / "test_model_pipeline.joblib"
        dummy_file.write_text("dummy serialized model bytes")
        return str(dummy_file)

    def test_mlops_service_model_promotion(self, admin_user, existing_pipeline_file):
        # 1. Create v1 (initially active)
        v1 = ModelVersion.objects.create(
            model_name='ClaimProbabilityPredictor',
            version='v1.0.0',
            algorithm_name='LogisticRegression',
            artifact_path=existing_pipeline_file,
            evaluation_metrics={'roc_auc': 0.58},
            is_active_for_inference=True,
        )

        # 2. Create v2 (initially inactive)
        v2 = ModelVersion.objects.create(
            model_name='ClaimProbabilityPredictor',
            version='v2.0.0',
            algorithm_name='RandomForestClassifier',
            artifact_path=existing_pipeline_file,
            evaluation_metrics={'roc_auc': 0.65},
            is_active_for_inference=False,
        )

        # 3. Promote v2
        promoted = MlopsService.promote_model(v2.id, activated_by=admin_user)
        assert promoted.is_active_for_inference is True

        # Refresh v1
        v1.refresh_from_db()
        assert v1.is_active_for_inference is False

        # Verify Compliance Audit Log
        audit = AuditLog.objects.filter(
            action='MODEL_VERSION_PROMOTED',
            target_entity='ModelVersion',
            target_id=str(v2.id),
        ).first()
        assert audit is not None
        assert audit.details['version'] == 'v2.0.0'
        assert audit.details['algorithm_name'] == 'RandomForestClassifier'

    def test_mlops_service_corrupted_or_missing_artifact_blocked(self, admin_user):
        missing = ModelVersion.objects.create(
            model_name='ClaimProbabilityPredictor',
            version='v3.0.0',
            algorithm_name='GradientBoostingClassifier',
            artifact_path='/nonexistent/path/to/corrupt_model.joblib',
            is_active_for_inference=False,
        )

        with pytest.raises(FileNotFoundError):
            MlopsService.promote_model(missing.id, activated_by=admin_user)

    def test_mlops_governance_metrics_aggregation(self):
        # Seed test inference logs
        PredictionLog.objects.create(
            prediction_type='CLAIM_RISK_AND_SEVERITY',
            confidence_or_probability=0.25,
            latency_ms=12.5,
            is_successful=True,
        )
        PredictionLog.objects.create(
            prediction_type='CLAIM_RISK_AND_SEVERITY',
            confidence_or_probability=0.45,
            latency_ms=17.5,
            is_successful=True,
        )
        PredictionLog.objects.create(
            prediction_type='CLAIM_RISK_AND_SEVERITY',
            confidence_or_probability=None,
            latency_ms=5.0,
            is_successful=False,
            error_message='Timeout simulating fault',
        )

        metrics = MlopsService.get_governance_metrics()
        assert metrics['total_predictions'] >= 3
        assert metrics['success_rate_pct'] == round((2 / 3) * 100.0, 2)
        assert metrics['avg_latency_ms'] > 0

    def test_mlops_service_version_comparison(self, existing_pipeline_file):
        ModelVersion.objects.create(
            model_name='SeverityModelComparison',
            version='v1.0.0',
            algorithm_name='Ridge',
            artifact_path=existing_pipeline_file,
            evaluation_metrics={'rmse': 2500},
            is_active_for_inference=False,
        )
        ModelVersion.objects.create(
            model_name='SeverityModelComparison',
            version='v2.0.0',
            algorithm_name='RandomForest',
            artifact_path=existing_pipeline_file,
            evaluation_metrics={'rmse': 2100},
            is_active_for_inference=True,
        )

        history = MlopsService.compare_versions('SeverityModelComparison')
        assert len(history) == 2
        versions = [h['version'] for h in history]
        assert 'v1.0.0' in versions
        assert 'v2.0.0' in versions

    def test_model_promote_view_rbac_and_execution(self, client, admin_user, customer_user, existing_pipeline_file):
        model = ModelVersion.objects.create(
            model_name='RBACModel',
            version='v1.0.0',
            algorithm_name='RandomForestClassifier',
            artifact_path=existing_pipeline_file,
            is_active_for_inference=False,
        )
        url = reverse('predictions:promote', kwargs={'pk': model.id})

        # 1. Unauthenticated -> redirect to login
        resp_unauth = client.post(url)
        assert resp_unauth.status_code == 302
        assert '/auth/login/' in resp_unauth.url

        # 2. Customer user -> 403 Forbidden
        client.force_login(customer_user)
        resp_cust = client.post(url)
        assert resp_cust.status_code == 403

        # 3. Administrator -> 302 redirect back to models with success
        client.force_login(admin_user)
        resp_admin = client.post(url)
        assert resp_admin.status_code == 302
        assert reverse('predictions:models') in resp_admin.url

        model.refresh_from_db()
        assert model.is_active_for_inference is True
