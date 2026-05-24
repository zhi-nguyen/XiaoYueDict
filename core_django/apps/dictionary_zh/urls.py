from django.urls import path
from .views import ZhWordSearchView

urlpatterns = [
    path('search/', ZhWordSearchView.as_view(), name='zh_word_search'),
]
