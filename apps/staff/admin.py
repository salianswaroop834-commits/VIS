from django.contrib import admin
from .models import StaffProfile, UnderwriterProfile, ClaimsHandlerProfile, Branch, StaffCustomerAssignment


class UnderwriterProfileInline(admin.StackedInline):
    model = UnderwriterProfile
    can_delete = False
    verbose_name = 'Underwriter Profile Details'
    verbose_name_plural = 'Underwriter Profile Details'
    readonly_fields = ('id', 'created_at', 'updated_at')
    extra = 0


class ClaimsHandlerProfileInline(admin.StackedInline):
    model = ClaimsHandlerProfile
    can_delete = False
    verbose_name = 'Claims Handler Profile Details'
    verbose_name_plural = 'Claims Handler Profile Details'
    readonly_fields = ('id', 'created_at', 'updated_at')
    extra = 0


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('city', 'state', 'branch_opening_date', 'office_rent_cost', 'is_active')
    list_filter = ('state', 'is_active')
    search_fields = ('city', 'state')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = (
        'staff_code',
        'get_email',
        'get_role',
        'department',
        'designation',
        'assigned_region',
        'status',
        'joining_date',
    )
    list_filter = ('department', 'status', 'assigned_region', 'user__role')
    search_fields = (
        'staff_code',
        'first_name',
        'last_name',
        'user__email',
        'user__first_name',
        'user__last_name',
        'designation',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [UnderwriterProfileInline, ClaimsHandlerProfileInline]
    ordering = ('staff_code',)

    @admin.display(description='User Email', ordering='user__email')
    def get_email(self, obj):
        return obj.user.email

    @admin.display(description='Role', ordering='user__role')
    def get_role(self, obj):
        return obj.user.get_role_display()


@admin.register(UnderwriterProfile)
class UnderwriterProfileAdmin(admin.ModelAdmin):
    list_display = (
        'get_staff_code',
        'get_email',
        'specialization',
        'underwriting_limit',
        'portfolio_name',
        'license_number',
        'status',
    )
    list_filter = ('status', 'specialization')
    search_fields = (
        'staff_profile__staff_code',
        'staff_profile__user__email',
        'license_number',
        'portfolio_name',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')

    @admin.display(description='Staff Code', ordering='staff_profile__staff_code')
    def get_staff_code(self, obj):
        return obj.staff_profile.staff_code

    @admin.display(description='Email', ordering='staff_profile__user__email')
    def get_email(self, obj):
        return obj.staff_profile.user.email


@admin.register(ClaimsHandlerProfile)
class ClaimsHandlerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'get_staff_code',
        'get_email',
        'specialization_team',
        'max_claim_approval_limit',
        'active_claim_capacity',
        'status',
    )
    list_filter = ('status', 'specialization_team')
    search_fields = (
        'staff_profile__staff_code',
        'staff_profile__user__email',
        'specialization_team',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')

    @admin.display(description='Staff Code', ordering='staff_profile__staff_code')
    def get_staff_code(self, obj):
        return obj.staff_profile.staff_code

    @admin.display(description='Email', ordering='staff_profile__user__email')
    def get_email(self, obj):
        return obj.staff_profile.user.email


@admin.register(StaffCustomerAssignment)
class StaffCustomerAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'staff',
        'get_customer_code',
        'get_customer_email',
        'status',
        'assigned_at',
        'assigned_by',
    )
    list_filter = ('status', 'assigned_at')
    search_fields = (
        'staff__email',
        'customer__customer_code',
        'customer__user__email',
        'assignment_reason',
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-assigned_at',)

    @admin.display(description='Customer Code', ordering='customer__customer_code')
    def get_customer_code(self, obj):
        return obj.customer.customer_code

    @admin.display(description='Customer Email', ordering='customer__user__email')
    def get_customer_email(self, obj):
        return obj.customer.user.email
