from django.contrib import admin
from apps.quotations.models import CoveragePlan, CoverageFeature, QuotationDraft


class CoverageFeatureInline(admin.TabularInline):
    model = CoverageFeature
    extra = 1


@admin.register(CoveragePlan)
class CoveragePlanAdmin(admin.ModelAdmin):
    list_display = (
        'plan_code',
        'name',
        'base_rate_percentage',
        'standard_deductible',
        'includes_own_damage',
        'includes_third_party',
        'includes_roadside_assistance',
        'includes_engine_protection',
        'is_active',
    )
    list_filter = ('is_active', 'includes_own_damage', 'includes_roadside_assistance')
    search_fields = ('plan_code', 'name', 'tagline')
    inlines = [CoverageFeatureInline]


@admin.register(CoverageFeature)
class CoverageFeatureAdmin(admin.ModelAdmin):
    list_display = ('feature_code', 'plan', 'title', 'is_standard', 'add_on_premium', 'is_active')
    list_filter = ('plan', 'is_standard', 'is_active')
    search_fields = ('feature_code', 'title', 'description')


@admin.register(QuotationDraft)
class QuotationDraftAdmin(admin.ModelAdmin):
    list_display = (
        'quotation_number',
        'customer',
        'coverage_plan',
        'vehicle_value',
        'calculated_premium',
        'status',
        'valid_until',
        'created_at',
    )
    list_filter = ('status', 'coverage_plan', 'duration_years')
    search_fields = ('quotation_number', 'customer__customer_code', 'customer__user__email')
    readonly_fields = ('created_at', 'updated_at')
