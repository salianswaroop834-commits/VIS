from django.contrib import admin
from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'customer_code',
        'get_email',
        'get_full_name',
        'city',
        'state',
        'is_identity_verified',
        'created_at',
    )
    list_filter = ('is_identity_verified', 'state', 'created_at')
    search_fields = (
        'customer_code',
        'user__email',
        'user__first_name',
        'user__last_name',
        'driving_license_number',
    )
    readonly_fields = ('id', 'customer_code', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    @admin.display(description='User Email', ordering='user__email')
    def get_email(self, obj):
        return obj.user.email

    @admin.display(description='Full Name')
    def get_full_name(self, obj):
        return obj.user.get_full_name() or '-'
