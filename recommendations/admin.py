from django.contrib import admin
from recommendations.models import CoverageRecommendation


@admin.register(CoverageRecommendation)
class CoverageRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'recommended_plan',
        'customer',
        'vehicle',
        'confidence_score',
        'created_at',
    )
    list_filter = ('recommended_plan',)
    search_fields = ('customer__customer_code', 'vehicle__registration_number', 'rationale')
    readonly_fields = ('created_at', 'updated_at')
