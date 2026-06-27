from django.contrib import admin
from .models import AssessmentTask

@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'language', 'status', 'queue_name', 'score', 'created_at')
    list_filter = ('language', 'status', 'queue_name', 'created_at')
    search_fields = ('id', 'user__username', 'user__email', 'target_text')
    readonly_fields = ('created_at',)
