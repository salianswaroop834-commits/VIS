from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, EmailOtpToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email',
        'username',
        'role',
        'phone_number',
        'is_active',
        'is_staff',
        'email_verified',
        'created_at',
    )
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'email_verified')
    search_fields = ('email', 'username', 'phone_number', 'supabase_uid')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'supabase_uid', 'created_at', 'updated_at', 'last_login', 'date_joined')

    fieldsets = (
        ('Identity & Credentials', {'fields': ('id', 'email', 'password')}),
        ('Personal Profile', {'fields': ('first_name', 'last_name', 'phone_number')}),
        ('Role & Platform Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Supabase Synchronization', {'fields': ('supabase_uid', 'email_verified')}),
        ('Audit Timestamps', {'fields': ('created_at', 'updated_at', 'last_login', 'date_joined')}),
    )


@admin.register(EmailOtpToken)
class EmailOtpTokenAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_used', 'attempts_count', 'expires_at', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('email',)
    readonly_fields = ('id', 'email', 'otp_hash', 'expires_at', 'created_at', 'is_used', 'attempts_count', 'user')

    def has_add_permission(self, request):
        # Tokens must be generated programmatically, not via admin panel
        return False
