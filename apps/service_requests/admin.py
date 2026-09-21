from django.contrib import admin
from apps.service_requests.models import ServiceRequest


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_number',
        'customer',
        'policy',
        'request_type',
        'title',
        'status',
        'assigned_staff',
        'created_at',
        'resolved_at',
    )
    list_filter = ('request_type', 'status')
    search_fields = (
        'request_number',
        'customer__customer_code',
        'customer__user__email',
        'title',
    )
    raw_id_fields = ('customer', 'policy', 'assigned_staff')
    readonly_fields = ('created_at', 'updated_at')
