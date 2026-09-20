from django.contrib import admin
from .models import CustomerProfile, KYCVerification, CustomerFeedback


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'customer_code',
        'get_email',
        'full_name',
        'city',
        'state',
        'is_identity_verified',
        'created_at',
    )
    list_filter = ('is_identity_verified', 'state', 'created_at')
    search_fields = (
        'customer_code',
        'first_name',
        'last_name',
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


@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'verification_type',
        'document_number_masked',
        'provider',
        'status',
        'verified_phone_masked',
        'verified_at',
        'created_at',
    )
    list_filter = ('status', 'verification_type', 'provider', 'created_at')
    search_fields = ('user__email', 'document_number_masked', 'provider_reference')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(CustomerFeedback)
class CustomerFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'nps_score', 'submitted_at')
    list_filter = ('nps_score', 'submitted_at')
    search_fields = ('user__email', 'comment')
    readonly_fields = ('id', 'submitted_at')
