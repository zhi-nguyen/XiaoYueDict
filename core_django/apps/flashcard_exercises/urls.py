from django.urls import path
from .views import GenerateExerciseView, CheckWritingView, CompleteExerciseView

urlpatterns = [
    path('exercises/', GenerateExerciseView.as_view(), name='generate_exercises'),
    path('exercises/complete/', CompleteExerciseView.as_view(), name='complete_exercise'),
    path('check-writing/', CheckWritingView.as_view(), name='check_writing'),
]
