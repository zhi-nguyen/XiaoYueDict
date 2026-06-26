from django.urls import path
from .views import ContentReportView

urlpatterns = [
    path('', ContentReportView.as_view(), name='create_report'),
]
