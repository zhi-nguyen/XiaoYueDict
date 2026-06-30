from rest_framework import generics, views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import UserStreak, DailyTarget, StudyHistory, DailyActivity
from .serializers import UserStreakSerializer, DailyTargetSerializer, StudyHistorySerializer, DailyActivitySerializer

class StreakView(generics.RetrieveAPIView):
    serializer_class = UserStreakSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        streak, _ = UserStreak.objects.get_or_create(user=self.request.user)
        return streak

class TargetView(generics.RetrieveUpdateAPIView):
    serializer_class = DailyTargetSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        target, _ = DailyTarget.objects.get_or_create(user=self.request.user)
        return target

class StudyHistoryLogView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve study history for the current user.
        """
        history = StudyHistory.objects.filter(user=request.user).order_by('-study_date')
        serializer = StudyHistorySerializer(history, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Increment the study history for today.
        Expects payload: {
            "vocabulary_learned": 5,
            "pronunciation_accuracy": 0.85,
            "study_duration_seconds": 300
        }
        """
        user = request.user
        today = timezone.localdate()

        vocab = request.data.get('vocabulary_learned', 0)
        acc = request.data.get('pronunciation_accuracy', 0.0)
        dur = request.data.get('study_duration_seconds', 0)

        history, created = StudyHistory.objects.get_or_create(user=user, study_date=today)
        
        # Calculate new average accuracy if needed, or simply keep the latest/highest.
        # For simplicity, if acc is provided, update it with an average.
        if acc > 0:
            if history.pronunciation_accuracy > 0:
                history.pronunciation_accuracy = (history.pronunciation_accuracy + acc) / 2.0
            else:
                history.pronunciation_accuracy = acc

        history.vocabulary_learned += int(vocab)
        history.study_duration_seconds += int(dur)
        history.save()

        # Immediately check if target met so user can see it without waiting for cron?
        # Typically gamification might show "Target Met!" immediately.
        # For performance, this is fine to do here for the current user.
        target, _ = DailyTarget.objects.get_or_create(user=user)
        is_met = False
        if target.target_type == 'words' and history.vocabulary_learned >= target.target_words:
            is_met = True
        elif target.target_type == 'duration' and history.study_duration_seconds >= (target.target_duration * 60):
            is_met = True
        
        if is_met:
            # We can mark it met for today, but the cron job will finalize streaks.
            # Or we can update the streak immediately if it wasn't met already.
            activity, created_act = DailyActivity.objects.get_or_create(user=user, activity_date=today)
            if not activity.is_target_met:
                activity.is_target_met = True
                activity.save()
                
                # We can dynamically increase the current streak immediately if we want real-time feedback
                # But to prevent double counting, the cron job should be the single source of truth for streak increments.

        return Response(StudyHistorySerializer(history).data, status=status.HTTP_200_OK)

from apps.dictionary_zh.views import StandardResultsSetPagination

class ActivityHistoryView(generics.ListAPIView):
    serializer_class = DailyActivitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return DailyActivity.objects.filter(user=self.request.user).order_by('-activity_date')


class GamificationDashboardView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        streak, _ = UserStreak.objects.get_or_create(user=user)
        target, _ = DailyTarget.objects.get_or_create(user=user)
        history = StudyHistory.objects.filter(user=user).order_by('-study_date')

        return Response({
            'streak': UserStreakSerializer(streak).data,
            'target': DailyTargetSerializer(target).data,
            'history': StudyHistorySerializer(history, many=True).data
        }, status=status.HTTP_200_OK)
