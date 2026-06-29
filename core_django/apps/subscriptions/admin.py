from django.contrib import admin
from .models import UserSubscription, SubscriptionHistory, VolumeLimitConfig, SubscriptionPlan, PaymentOrder

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('tier', 'price', 'vat', 'total_price', 'updated_at')
    list_filter = ('tier',)
    search_fields = ('tier',)

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'pending_downgrade_tier', 'price', 'vat', 'total_price_display', 'start_date', 'end_date', 'is_active')
    list_filter = ('tier', 'is_active', 'pending_downgrade_tier')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('total_price_display',)

    def total_price_display(self, obj):
        return f"{obj.total_price:.2f}"
    total_price_display.short_description = "Tổng giá (gồm VAT)"

@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'action', 'changed_at', 'note')
    list_filter = ('tier', 'action')
    search_fields = ('user__username', 'user__email', 'note')

@admin.register(VolumeLimitConfig)
class VolumeLimitConfigAdmin(admin.ModelAdmin):
    list_display = ('tier', 'mb_per_minute', 'mb_per_hour', 'mb_per_day', 'pdf_daily_limit', 'pdf_word_limit')
    list_filter = ('tier',)
    search_fields = ('tier',)

@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('order_code', 'user', 'target_tier', 'amount', 'status', 'created_at', 'expires_at', 'paid_at')
    list_filter = ('status', 'target_tier')
    search_fields = ('order_code', 'user__username', 'user__email', 'sepay_transaction_id')
    readonly_fields = ('id', 'order_code', 'sepay_transaction_id', 'bank_reference', 'created_at', 'paid_at')
