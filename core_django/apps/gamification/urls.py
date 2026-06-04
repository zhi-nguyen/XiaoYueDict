from django.urls import path
from .views import StreakView, TargetView, StudyHistoryLogView, ActivityHistoryView

urlpatterns = [
    path('streaks/', StreakView.as_view(), name='my-streaks'),
    path('targets/', TargetView.as_view(), name='my-targets'),
    path('history/', StudyHistoryLogView.as_view(), name='log-history'),
    path('activities/', ActivityHistoryView.as_view(), name='my-activities'),
]
