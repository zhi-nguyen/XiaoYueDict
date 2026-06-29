from django.urls import path
from .views import (
    MySubscriptionView, 
    SubscriptionHistoryListView, 
    SubscriptionUsageView,
    SubscriptionPlanListView,
    SubscriptionRegisterView,
    CancelDowngradeView,
    SePayWebhookView,
    PaymentStatusView,
)

urlpatterns = [
    path('me/', MySubscriptionView.as_view(), name='my-subscription'),
    path('history/', SubscriptionHistoryListView.as_view(), name='subscription-history'),
    path('usage/', SubscriptionUsageView.as_view(), name='subscription-usage'),
    path('plans/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
    path('register/', SubscriptionRegisterView.as_view(), name='subscription-register'),
    path('cancel-downgrade/', CancelDowngradeView.as_view(), name='cancel-downgrade'),
    path('sepay-webhook/', SePayWebhookView.as_view(), name='sepay-webhook'),
    path('payment-status/<uuid:order_id>/', PaymentStatusView.as_view(), name='payment-status'),
]
