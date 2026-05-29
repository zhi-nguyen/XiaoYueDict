from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import UserSubscription, SubscriptionHistory
from .serializers import UserSubscriptionSerializer, SubscriptionHistorySerializer

class MySubscriptionView(generics.RetrieveAPIView):
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Trigger check_validity on fetch to auto-downgrade expired subs
        sub = getattr(self.request.user, 'subscription', None)
        if sub:
            sub.check_validity()
        return sub

class SubscriptionHistoryListView(generics.ListAPIView):
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SubscriptionHistory.objects.filter(user=self.request.user).order_by('-changed_at')
