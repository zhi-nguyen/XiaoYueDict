from django.db import models
from django.conf import settings
from django.utils import timezone

class UserStreak(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='streak')
    current_streak = models.IntegerField(default=0)
    max_streak = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - Streak: {self.current_streak}"

class DailyTarget(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_target')
    target_words = models.IntegerField(default=10)
    target_duration = models.IntegerField(default=15) # in minutes
    target_type = models.CharField(max_length=50, default='words') # 'words' or 'duration'

    def __str__(self):
        return f"{self.user.username} Target: {self.target_words} words"

class StudyHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='study_histories')
    study_date = models.DateField(default=timezone.now)
    vocabulary_learned = models.IntegerField(default=0)
    pronunciation_accuracy = models.FloatField(default=0.0)
    study_duration_seconds = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'study_date')

    def __str__(self):
        return f"{self.user.username} - {self.study_date}"

class DailyActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_activities')
    activity_date = models.DateField(default=timezone.now)
    is_target_met = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'activity_date')

    def __str__(self):
        return f"{self.user.username} - {self.activity_date} - Met: {self.is_target_met}"
