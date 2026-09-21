from django.contrib import admin
from apps.vehicles.models import Vehicle, VehicleModelSpec, AreaRisk


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        'registration_number',
        'customer',
        'make',
        'model',
        'variant',
        'manufacture_year',
        'vehicle_type',
        'fuel_type',
        'vehicle_value',
        'is_active',
    )
    list_filter = ('vehicle_type', 'fuel_type', 'usage_type', 'is_active')
    search_fields = ('registration_number', 'chassis_number', 'customer__customer_code', 'customer__user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(VehicleModelSpec)
class VehicleModelSpecAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'variant', 'segment', 'fuel_type', 'base_price', 'ncap_rating')
    list_filter = ('make', 'segment', 'fuel_type')
    search_fields = ('make', 'model', 'variant')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AreaRisk)
class AreaRiskAdmin(admin.ModelAdmin):
    list_display = ('city', 'state', 'vehicle_theft_rate_area', 'accident_hotspot_flag', 'avg_repair_cost_area')
    list_filter = ('state', 'accident_hotspot_flag')
    search_fields = ('city', 'state')
    readonly_fields = ('id', 'created_at', 'updated_at')
