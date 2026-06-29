from django.urls import path
from .views import GetWordImageView, ReportInvalidImageView
from .tts_views import TriggerTTSView

urlpatterns = [
    path('image/report/', ReportInvalidImageView.as_view(), name='report_invalid_image'),
    path('image/<str:lang>/<uuid:word_id>/', GetWordImageView.as_view(), name='get_word_image'),
    path('tts/', TriggerTTSView.as_view(), name='trigger_tts_generation'),
]
