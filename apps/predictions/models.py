from django.db import models
from core.models import AuditableModel


class ModelLifecycleStatus(models.TextChoices):
    TRAINED = 'TRAINED', 'Trained'
    EVALUATED = 'EVALUATED', 'Evaluated'
    CANDIDATE = 'CANDIDATE', 'Candidate'
    APPROVED = 'APPROVED', 'Approved'
    ACTIVE = 'ACTIVE', 'Active (Live)'
    RETIRED = 'RETIRED', 'Retired'


class ModelVersion(AuditableModel):
    """
    ML Model Registry tracking versions, algorithms, evaluation metrics,
    lifecycle state transitions, and deployment state for MLOps compliance.
    """
    model_name = models.CharField(max_length=100, db_index=True)
    version = models.CharField(max_length=50, db_index=True)
    algorithm_name = models.CharField(max_length=100)
    hyperparameters = models.JSONField(default=dict)
    evaluation_metrics = models.JSONField(default=dict)
    artifact_path = models.CharField(max_length=255)
    training_dataset_version = models.CharField(max_length=50, default='synthetic_v1')
    feature_version = models.CharField(max_length=50, default='v1.0')
    status = models.CharField(
        max_length=30,
        choices=ModelLifecycleStatus.choices,
        default=ModelLifecycleStatus.TRAINED,
        db_index=True,
    )
    deployment_status = models.CharField(max_length=50, default='STAGING')
    is_active_for_inference = models.BooleanField(default=False, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Model Version'
        verbose_name_plural = 'Model Versions'
        unique_together = ('model_name', 'version')
        ordering = ['-created_at']

    def __str__(self):
        status = 'ACTIVE' if self.is_active_for_inference else 'ARCHIVED'
        return f"{self.model_name} [{self.version}] ({status})"


class PredictionLog(AuditableModel):
    """
    Structured log of all ML inferences for governance, monitoring, and auditability.
    Enforces that inference outputs are marked as decision-support indicators.
    """
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prediction_logs',
    )
    prediction_type = models.CharField(max_length=50, db_index=True)
    input_payload = models.JSONField(default=dict)
    output_result = models.JSONField(default=dict)
    confidence_or_probability = models.FloatField(null=True, blank=True)
    latency_ms = models.FloatField(default=0.0)
    is_successful = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    disclaimer = models.TextField(
        default='ML estimation signal only. Not an automated claim decision.'
    )
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_predictions',
    )

    class Meta:
        verbose_name = 'Prediction Log'
        verbose_name_plural = 'Prediction Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Prediction: {self.prediction_type} at {self.created_at} (Success: {self.is_successful})"
