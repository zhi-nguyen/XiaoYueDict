from django.urls import path
from .views import (
    ContentReportView,
    FeatureReportView,
    SupportRequestView,
    SupportRequestDetailView,
    GuestTicketVerifyView,
    GuestTicketBulkVerifyView,
)

urlpatterns = [
    path('', ContentReportView.as_view(), name='create_report'),
    path('features/', FeatureReportView.as_view(), name='feature_reports'),
    path('support/', SupportRequestView.as_view(), name='support_requests'),
    # verify routes MUST be before <uuid:pk> to avoid matching "verify" as UUID
    path('support/verify/', GuestTicketVerifyView.as_view(), name='guest_ticket_verify'),
    path('support/verify-bulk/', GuestTicketBulkVerifyView.as_view(), name='guest_ticket_bulk_verify'),
    path('support/<uuid:pk>/', SupportRequestDetailView.as_view(), name='support_request_detail'),
]
