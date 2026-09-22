from django.contrib import admin
from apps.payments.models import SimulatedPayment


@admin.register(SimulatedPayment)
class SimulatedPaymentAdmin(admin.ModelAdmin):
    list_display = (
        'simulated_transaction_id',
        'amount',
        'currency',
        'card_network',
        'masked_card_number',
        'is_successful',
        'created_at',
    )
    list_filter = ('card_network', 'is_successful')
    search_fields = ('simulated_transaction_id', 'masked_card_number')
    readonly_fields = ('created_at', 'updated_at')
