from django.contrib import admin
from vehicles.models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        'registration_number',
        'customer',
        'make',
        'model',
        'manufacture_year',
        'vehicle_type',
        'fuel_type',
        'vehicle_value',
        'is_active',
    )
    list_filter = ('vehicle_type', 'fuel_type', 'usage_type', 'is_active')
    search_fields = ('registration_number', 'chassis_number', 'customer__customer_code', 'customer__user__email')
    readonly_fields = ('created_at', 'updated_at')
