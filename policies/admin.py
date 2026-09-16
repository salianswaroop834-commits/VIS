from django.contrib import admin
from policies.models import Policy


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        'policy_number',
        'customer',
        'vehicle',
        'coverage_plan',
        'underwriter',
        'premium_amount',
        'start_date',
        'end_date',
        'status',
        'previous_policy',
    )
    list_filter = ('status', 'coverage_plan', 'duration_years')
    search_fields = (
        'policy_number',
        'customer__customer_code',
        'customer__user__email',
        'vehicle__registration_number',
    )
    raw_id_fields = ('customer', 'vehicle', 'underwriter', 'previous_policy')
    readonly_fields = ('created_at', 'updated_at')
