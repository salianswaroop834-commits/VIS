from django.contrib import admin
from apps.claims.models import Claim, ClaimDocument, ClaimEvent


class ClaimDocumentInline(admin.TabularInline):
    model = ClaimDocument
    extra = 0
    readonly_fields = ('created_at',)


class ClaimEventInline(admin.TabularInline):
    model = ClaimEvent
    extra = 0
    readonly_fields = ('created_at', 'event_type', 'actor', 'actor_role', 'notes')
    can_delete = False


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = (
        'claim_number',
        'customer',
        'policy',
        'handler',
        'incident_date',
        'estimated_loss_amount',
        'settlement_amount',
        'status',
        'created_at',
    )
    list_filter = ('status', 'incident_date')
    search_fields = (
        'claim_number',
        'policy__policy_number',
        'customer__customer_code',
        'customer__user__email',
    )
    raw_id_fields = ('customer', 'policy', 'handler')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ClaimDocumentInline, ClaimEventInline]


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'claim', 'document_type', 'created_at')
    list_filter = ('document_type',)
    search_fields = ('title', 'claim__claim_number')


@admin.register(ClaimEvent)
class ClaimEventAdmin(admin.ModelAdmin):
    list_display = ('claim', 'event_type', 'actor', 'actor_role', 'created_at')
    list_filter = ('event_type', 'actor_role')
    search_fields = ('claim__claim_number', 'notes')
    readonly_fields = ('created_at',)
