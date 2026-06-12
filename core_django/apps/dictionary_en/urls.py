from django.urls import path
from .views import EnWordSearchView, EnPureTextTranslationView, EnTranslationStatusView

urlpatterns = [
    path('search/', EnWordSearchView.as_view(), name='en_word_search'),
    path('translate/', EnPureTextTranslationView.as_view(), name='en_translate'),
    path('translate/status/<str:task_id>/', EnTranslationStatusView.as_view(), name='en_translate_status'),
]
