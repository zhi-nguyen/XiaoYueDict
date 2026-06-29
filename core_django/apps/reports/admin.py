from django.contrib import admin
from django.utils import timezone
from .models import ContentReport, FeatureReport, SupportRequest, TicketComment


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


@admin.register(FeatureReport)
class FeatureReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'feature_area', 'reporter', 'status', 'created_at')
    list_filter = ('status', 'feature_area', 'created_at')
    search_fields = ('title', 'description', 'guest_id')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['mark_planned', 'mark_implemented', 'mark_dismissed']

    def mark_planned(self, request, queryset):
        queryset.update(status='planned')
    mark_planned.short_description = "Đánh dấu đã lên kế hoạch"

    def mark_implemented(self, request, queryset):
        queryset.update(status='implemented')
    mark_implemented.short_description = "Đánh dấu đã triển khai"

    def mark_dismissed(self, request, queryset):
        queryset.update(status='dismissed')
    mark_dismissed.short_description = "Đánh dấu bỏ qua"


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 1
    readonly_fields = ('created_at',)
    fields = ('author', 'comment_text', 'is_internal', 'created_at')


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'priority', 'reporter', 'guest_email', 'status', 'created_at')
    list_filter = ('status', 'category', 'priority', 'created_at')
    search_fields = ('title', 'description', 'guest_id', 'guest_email', 'guest_name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TicketCommentInline]
    actions = ['mark_in_progress', 'mark_resolved', 'mark_closed']

    def mark_in_progress(self, request, queryset):
        queryset.update(status='in_progress')
    mark_in_progress.short_description = "Chuyển sang Đang xử lý"

    def mark_resolved(self, request, queryset):
        queryset.update(status='resolved')
    mark_resolved.short_description = "Đánh dấu đã giải quyết"

    def mark_closed(self, request, queryset):
        queryset.update(status='closed')
    mark_closed.short_description = "Đánh dấu đã đóng"
