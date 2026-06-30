from django.contrib import admin
from .models import FlashcardExercise, UserFlashcardHistory


@admin.register(FlashcardExercise)
class FlashcardExerciseAdmin(admin.ModelAdmin):
    list_display = ['id', 'word', 'lang', 'exercise_type', 'created_at']
    search_fields = ['word']
    list_filter = ['lang', 'exercise_type']


@admin.register(UserFlashcardHistory)
class UserFlashcardHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'word', 'lang', 'exercise_type', 'completed_at']
    search_fields = ['word', 'user__email']
    list_filter = ['lang', 'exercise_type']
