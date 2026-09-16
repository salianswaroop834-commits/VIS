from django.contrib import admin
from predictions.models import ModelVersion, PredictionLog


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = (
        'model_name',
        'version',
        'algorithm_name',
        'training_dataset_version',
        'is_active_for_inference',
        'created_at',
    )
    list_filter = ('model_name', 'is_active_for_inference')
    search_fields = ('model_name', 'version', 'algorithm_name')


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display = (
        'prediction_type',
        'model_version',
        'confidence_or_probability',
        'latency_ms',
        'is_successful',
        'created_at',
    )
    list_filter = ('prediction_type', 'is_successful')
    search_fields = ('prediction_type', 'error_message')
    readonly_fields = ('created_at', 'updated_at')
