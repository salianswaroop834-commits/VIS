from django.contrib import admin
from apps.policies.models import Policy, Addon, PolicyAddon


class PolicyAddonInline(admin.TabularInline):
    model = PolicyAddon
    extra = 1
    readonly_fields = ('created_at',)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        'policy_number',
        'customer',
        'vehicle',
        'coverage_plan',
        'assigned_staff',
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
    raw_id_fields = ('customer', 'vehicle', 'assigned_staff', 'previous_policy')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PolicyAddonInline]


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = ('addon_name', 'addon_code', 'addon_cost', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('addon_name', 'addon_code')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(PolicyAddon)
class PolicyAddonAdmin(admin.ModelAdmin):
    list_display = ('policy', 'addon', 'price_at_purchase', 'created_at')
    raw_id_fields = ('policy', 'addon')
    readonly_fields = ('id', 'created_at', 'updated_at')
