from django.contrib import admin
from django.utils import timezone
from .models import ContentReport

@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ('report_type', 'content_type', 'object_id', 'reporter', 'status', 'created_at')
    list_filter = ('status', 'report_type', 'content_type', 'created_at')
    search_fields = ('object_id', 'reason', 'suggested_correction', 'guest_id')
    readonly_fields = ('created_at',)
    actions = ['mark_resolved', 'mark_dismissed']

    def mark_resolved(self, request, queryset):
        queryset.update(status='resolved', resolved_at=timezone.now())
    mark_resolved.short_description = "Đánh dấu là đã giải quyết"

    def mark_dismissed(self, request, queryset):
        queryset.update(status='dismissed', resolved_at=timezone.now())
    mark_dismissed.short_description = "Đánh dấu là bỏ qua"
