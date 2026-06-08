from django.contrib import admin
from .models import UserSubscription, SubscriptionHistory, VolumeLimitConfig

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'start_date', 'end_date', 'is_active')
    list_filter = ('tier', 'is_active')
    search_fields = ('user__username', 'user__email')

@admin.register(SubscriptionHistory)
class SubscriptionHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'action', 'changed_at', 'note')
    list_filter = ('tier', 'action')
    search_fields = ('user__username', 'user__email', 'note')

@admin.register(VolumeLimitConfig)
class VolumeLimitConfigAdmin(admin.ModelAdmin):
    list_display = ('tier', 'mb_per_minute', 'mb_per_hour', 'mb_per_day')
    list_filter = ('tier',)
    search_fields = ('tier',)
