from django.urls import path
from .views import ZhWordSearchView, ZhWordBatchSearchView, PureTextTranslationView, TranslationStatusView

urlpatterns = [
    path('search/', ZhWordSearchView.as_view(), name='zh_word_search'),
    path('search/batch/', ZhWordBatchSearchView.as_view(), name='zh_word_batch_search'),
    path('translate/', PureTextTranslationView.as_view(), name='zh_translate'),
    path('translate/status/<str:task_id>/', TranslationStatusView.as_view(), name='zh_translate_status'),
]
