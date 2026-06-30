from django.urls import path
from .views import (
    NotebookListCreateView,
    NotebookDetailView,
    WordListCreateView,
    WordDetailView,
    DictionaryLookupView,
    NotebookExportPDFView,
    PDFExportStatusView,
    PDFExportDownloadView,
    PDFExportLimitsView,
    SystemNotebookListView,
    SystemNotebookWordsView,
    CloneSystemNotebookView,
)

urlpatterns = [
    # Clone system notebook
    path('clone-system-notebook/', CloneSystemNotebookView.as_view(), name='clone_system_notebook'),

    # Notebook CRUD
    path('notebooks/', NotebookListCreateView.as_view(), name='notebook_list_create'),
    path('notebooks/<uuid:notebook_id>/', NotebookDetailView.as_view(), name='notebook_detail'),
    
    # PDF Export System (Asynchronous queue)
    path('notebooks/<uuid:notebook_id>/export-pdf/', NotebookExportPDFView.as_view(), name='notebook_export_pdf'),
    path('notebooks/<uuid:notebook_id>/export-pdf/limits/', PDFExportLimitsView.as_view(), name='pdf_export_limits'),
    path('notebooks/export-pdf/status/<uuid:task_id>/', PDFExportStatusView.as_view(), name='pdf_export_status'),
    path('notebooks/export-pdf/download/<uuid:task_id>/', PDFExportDownloadView.as_view(), name='pdf_export_download'),

    # Word CRUD (nested under notebook)
    path('notebooks/<uuid:notebook_id>/words/', WordListCreateView.as_view(), name='word_list_create'),
    path('notebooks/<uuid:notebook_id>/words/<uuid:word_id>/', WordDetailView.as_view(), name='word_detail'),

    # Dictionary lookup
    path('lookup/', DictionaryLookupView.as_view(), name='dictionary_lookup'),

    # System default notebooks
    path('system-notebooks/', SystemNotebookListView.as_view(), name='system_notebook_list'),
    path('system-notebooks/<str:key>/words/', SystemNotebookWordsView.as_view(), name='system_notebook_words'),
]
