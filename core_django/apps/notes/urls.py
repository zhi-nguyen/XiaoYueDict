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
)

urlpatterns = [
    # Notebook CRUD
    path('notebooks/', NotebookListCreateView.as_view(), name='notebook_list_create'),
    path('notebooks/<int:notebook_id>/', NotebookDetailView.as_view(), name='notebook_detail'),
    
    # PDF Export System (Asynchronous queue)
    path('notebooks/<int:notebook_id>/export-pdf/', NotebookExportPDFView.as_view(), name='notebook_export_pdf'),
    path('notebooks/<int:notebook_id>/export-pdf/limits/', PDFExportLimitsView.as_view(), name='pdf_export_limits'),
    path('notebooks/export-pdf/status/<uuid:task_id>/', PDFExportStatusView.as_view(), name='pdf_export_status'),
    path('notebooks/export-pdf/download/<uuid:task_id>/', PDFExportDownloadView.as_view(), name='pdf_export_download'),

    # Word CRUD (nested under notebook)
    path('notebooks/<int:notebook_id>/words/', WordListCreateView.as_view(), name='word_list_create'),
    path('notebooks/<int:notebook_id>/words/<int:word_id>/', WordDetailView.as_view(), name='word_detail'),

    # Dictionary lookup
    path('lookup/', DictionaryLookupView.as_view(), name='dictionary_lookup'),
]
