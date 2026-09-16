from django.contrib import admin
from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'action',
        'target_entity',
        'target_id',
        'actor_email',
        'actor_role',
        'is_success',
    )
    list_filter = ('action', 'target_entity', 'is_success', 'created_at')
    search_fields = ('actor_email', 'target_id', 'action', 'target_entity')
    readonly_fields = (
        'id',
        'actor',
        'actor_email',
        'actor_role',
        'action',
        'target_entity',
        'target_id',
        'details',
        'ip_address',
        'is_success',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
