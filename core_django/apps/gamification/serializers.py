from rest_framework import serializers
from .models import UserStreak, DailyTarget, StudyHistory, DailyActivity

class UserStreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStreak
        fields = ['current_streak', 'max_streak']

class DailyTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyTarget
        fields = ['target_words', 'target_duration', 'target_type']

class StudyHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyHistory
        fields = ['study_date', 'vocabulary_learned', 'pronunciation_accuracy', 'study_duration_seconds']
        read_only_fields = ['study_date']

class DailyActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyActivity
        fields = ['activity_date', 'is_target_met']
