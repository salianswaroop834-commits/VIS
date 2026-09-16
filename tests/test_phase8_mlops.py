import pytest
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model

from accounts.models import UserRole
from predictions.models import ModelVersion, ModelLifecycleStatus, PredictionLog
from predictions.services.mlops_service import MlopsService
from audit.models import AuditLog

User = get_user_model()


@pytest.fixture
def mlops_users(db):
    customer = User.objects.create_user(
        username='mlops_customer',
        email='mlops_cust@nexisure.test',
        password='Password123!',
        role=UserRole.CUSTOMER,
        email_verified=True,
    )
    underwriter = User.objects.create_user(
        username='mlops_underwriter',
        email='mlops_uw@nexisure.test',
        password='Password123!',
        role=UserRole.UNDERWRITER,
        email_verified=True,
        is_staff=True,
    )
    admin = User.objects.create_user(
        username='mlops_admin',
        email='mlops_admin@nexisure.test',
        password='Password123!',
        role=UserRole.ADMINISTRATOR,
        email_verified=True,
        is_staff=True,
        is_superuser=True,
    )
    return {
        'customer': customer,
        'underwriter': underwriter,
        'admin': admin,
    }


@pytest.fixture
def sample_model_registry(db):
    # Model 1: Initial Active Version
    m1 = ModelVersion.objects.create(
        model_name='ClaimProbabilityPredictor',
        version='1.0.0',
        algorithm_name='LogisticRegression',
        status=ModelLifecycleStatus.ACTIVE,
        is_active_for_inference=True,
        deployment_status='PRODUCTION',
        evaluation_metrics={'accuracy': 0.858, 'roc_auc': 0.589, 'f1_score': 0.045},
    )

    # Model 2: Candidate in Evaluated status
    m2 = ModelVersion.objects.create(
        model_name='ClaimProbabilityPredictor',
        version='1.1.0',
        algorithm_name='GradientBoostingClassifier',
        status=ModelLifecycleStatus.EVALUATED,
        is_active_for_inference=False,
        deployment_status='STAGING',
        evaluation_metrics={'accuracy': 0.862, 'roc_auc': 0.625, 'f1_score': 0.120},
    )

    # Model 3: Regressor in Approved status
    m3 = ModelVersion.objects.create(
        model_name='ClaimSeverityPredictor',
        version='1.0.0',
        algorithm_name='RidgeRegression',
        status=ModelLifecycleStatus.APPROVED,
        is_active_for_inference=False,
        deployment_status='STAGING',
        evaluation_metrics={'mae': 2286.0, 'rmse': 3034.0, 'r2_score': -0.94},
    )

    return {'active_clf': m1, 'candidate_clf': m2, 'approved_reg': m3}


@pytest.mark.django_db
class TestPhase8ModelRegistryAndUniqueness:

    def test_model_version_uniqueness(self, sample_model_registry):
        """ModelVersion must enforce uniqueness constraint on (model_name, version)."""
        with pytest.raises(IntegrityError):
            ModelVersion.objects.create(
                model_name='ClaimProbabilityPredictor',
                version='1.0.0',
                algorithm_name='DuplicateAlgorithm',
            )

    def test_registry_metadata_fields(self, sample_model_registry):
        """Verifies metadata fields: model_name, version, algorithm, status, feature_version, metrics."""
        m = sample_model_registry['active_clf']
        assert m.model_name == 'ClaimProbabilityPredictor'
        assert m.version == '1.0.0'
        assert m.algorithm_name == 'LogisticRegression'
        assert m.status == ModelLifecycleStatus.ACTIVE
        assert m.is_active_for_inference is True
        assert m.deployment_status == 'PRODUCTION'
        assert 'roc_auc' in m.evaluation_metrics


@pytest.mark.django_db
class TestPhase8ModelPromotionAndLifecycle:

    def test_unauthorized_promotion_rejected(self, mlops_users, sample_model_registry):
        """Customers must not be allowed to promote model versions."""
        candidate = sample_model_registry['candidate_clf']
        with pytest.raises(PermissionDenied):
            MlopsService.promote_model(
                candidate.id,
                target_status=ModelLifecycleStatus.CANDIDATE,
                actor=mlops_users['customer']
            )

    def test_invalid_lifecycle_transition_rejected(self, mlops_users, sample_model_registry):
        """Direct transition from EVALUATED to ACTIVE is forbidden (must pass through CANDIDATE & APPROVED)."""
        candidate = sample_model_registry['candidate_clf']
        with pytest.raises(ValueError) as exc:
            MlopsService.promote_model(
                candidate.id,
                target_status=ModelLifecycleStatus.ACTIVE,
                actor=mlops_users['admin']
            )
        assert "Invalid model lifecycle transition" in str(exc.value)

    def test_complete_lifecycle_promotion_and_deactivation(self, mlops_users, sample_model_registry):
        """Promoting candidate from EVALUATED -> CANDIDATE -> APPROVED -> ACTIVE deactivates old active model."""
        old_active = sample_model_registry['active_clf']
        candidate = sample_model_registry['candidate_clf']
        admin = mlops_users['admin']

        # 1. EVALUATED -> CANDIDATE
        c1 = MlopsService.promote_model(candidate.id, ModelLifecycleStatus.CANDIDATE, actor=admin)
        assert c1.status == ModelLifecycleStatus.CANDIDATE

        # 2. CANDIDATE -> APPROVED
        c2 = MlopsService.promote_model(candidate.id, ModelLifecycleStatus.APPROVED, actor=admin)
        assert c2.status == ModelLifecycleStatus.APPROVED

        # 3. APPROVED -> ACTIVE
        c3 = MlopsService.promote_model(candidate.id, ModelLifecycleStatus.ACTIVE, actor=admin)
        assert c3.status == ModelLifecycleStatus.ACTIVE
        assert c3.is_active_for_inference is True
        assert c3.deployment_status == 'PRODUCTION'

        # Old active model must be automatically retired and deactivated
        old_active.refresh_from_db()
        assert old_active.is_active_for_inference is False
        assert old_active.status == ModelLifecycleStatus.RETIRED

    def test_promotion_generates_audit_log(self, mlops_users, sample_model_registry):
        """Every promotion generates an immutable audit record."""
        reg = sample_model_registry['approved_reg']
        uw = mlops_users['underwriter']

        initial_audits = AuditLog.objects.filter(action='MODEL_VERSION_PROMOTED').count()
        MlopsService.promote_model(reg.id, ModelLifecycleStatus.ACTIVE, actor=uw)

        new_audits = AuditLog.objects.filter(action='MODEL_VERSION_PROMOTED').count()
        assert new_audits == initial_audits + 1

        last_audit = AuditLog.objects.filter(action='MODEL_VERSION_PROMOTED').first()
        assert last_audit.actor == uw
        assert last_audit.target_entity == 'ModelVersion'
        assert str(reg.id) == last_audit.target_id

    def test_retirement_of_model(self, mlops_users, sample_model_registry):
        """Active model can be explicitly retired."""
        active = sample_model_registry['active_clf']
        admin = mlops_users['admin']

        retired = MlopsService.promote_model(active.id, ModelLifecycleStatus.RETIRED, actor=admin)
        assert retired.status == ModelLifecycleStatus.RETIRED
        assert retired.is_active_for_inference is False
        assert retired.deployment_status == 'ARCHIVED'


@pytest.mark.django_db
class TestPhase8ModelComparisonAndShadowDeployment:

    def test_model_comparison_structure(self, sample_model_registry):
        """Verifies multi-metric comparison table across candidates."""
        comparison = MlopsService.compare_models()
        assert len(comparison) >= 2
        for comp in comparison:
            assert 'model_name' in comp
            assert 'version' in comp
            assert 'algorithm' in comp
            assert 'metrics' in comp
            assert 'notice' in comp
            assert 'Automated promotion solely on one metric is prohibited' in comp['notice']

    def test_shadow_model_evaluation_isolation(self, sample_model_registry):
        """Candidate model evaluation runs in shadow mode without altering business logic or contracts."""
        candidate = sample_model_registry['candidate_clf']
        assert candidate.is_active_for_inference is False

        payload = {'vehicle_age': 2, 'vehicle_value': 800000.0}
        shadow_result = MlopsService.evaluate_shadow_model(candidate.id, payload)

        assert shadow_result['shadow_mode'] is True
        assert shadow_result['candidate_version'] == '1.1.0'
        assert shadow_result['candidate_status'] == ModelLifecycleStatus.EVALUATED
        assert 'prediction_result' in shadow_result

        # Candidate must remain inactive
        candidate.refresh_from_db()
        assert candidate.is_active_for_inference is False

        # Log must be stored as SHADOW_INFERENCE
        log = PredictionLog.objects.get(id=shadow_result['prediction_log_id'])
        assert log.prediction_type == 'SHADOW_INFERENCE'
        assert 'SHADOW MODE ONLY' in log.disclaimer

    def test_drift_telemetry_monitoring(self):
        """Verifies drift monitoring reports feature distributions, tier breakdown, and sample size."""
        telemetry = MlopsService.get_drift_telemetry()
        assert telemetry['status'] == 'MONITORING_ACTIVE'
        assert 'sample_size' in telemetry
        assert 'feature_distributions' in telemetry
        assert 'risk_tier_distribution' in telemetry
        assert 'missing_value_rate_pct' in telemetry
