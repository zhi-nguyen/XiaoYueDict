from django.urls import path
from .views import MySubscriptionView, SubscriptionHistoryListView, SubscriptionUsageView

urlpatterns = [
    path('me/', MySubscriptionView.as_view(), name='my-subscription'),
    path('history/', SubscriptionHistoryListView.as_view(), name='subscription-history'),
    path('usage/', SubscriptionUsageView.as_view(), name='subscription-usage'),
]

