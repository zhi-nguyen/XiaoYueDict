from django.contrib import admin
from .models import UserStreak, DailyTarget, StudyHistory, DailyActivity

@admin.register(UserStreak)
class UserStreakAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_streak', 'max_streak')
    search_fields = ('user__username', 'user__email')

@admin.register(DailyTarget)
class DailyTargetAdmin(admin.ModelAdmin):
    list_display = ('user', 'target_words', 'target_duration', 'target_type')
    search_fields = ('user__username', 'user__email')

@admin.register(StudyHistory)
class StudyHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'study_date', 'vocabulary_learned', 'pronunciation_accuracy', 'study_duration_seconds')
    list_filter = ('study_date',)
    search_fields = ('user__username', 'user__email')

@admin.register(DailyActivity)
class DailyActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_date', 'is_target_met')
    list_filter = ('activity_date', 'is_target_met')
    search_fields = ('user__username', 'user__email')
