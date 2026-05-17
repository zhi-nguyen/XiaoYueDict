from django.urls import path
from .views import (
    NotebookListCreateView,
    NotebookDetailView,
    WordListCreateView,
    WordDetailView,
    DictionaryLookupView,
)

urlpatterns = [
    # Notebook CRUD
    path('notebooks/', NotebookListCreateView.as_view(), name='notebook_list_create'),
    path('notebooks/<int:notebook_id>/', NotebookDetailView.as_view(), name='notebook_detail'),

    # Word CRUD (nested under notebook)
    path('notebooks/<int:notebook_id>/words/', WordListCreateView.as_view(), name='word_list_create'),
    path('notebooks/<int:notebook_id>/words/<int:word_id>/', WordDetailView.as_view(), name='word_detail'),

    # Dictionary lookup
    path('lookup/', DictionaryLookupView.as_view(), name='dictionary_lookup'),
]
