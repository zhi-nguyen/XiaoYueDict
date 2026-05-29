from rest_framework import serializers
from .models import UserSubscription, SubscriptionHistory

class UserSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSubscription
        fields = ['tier', 'start_date', 'end_date', 'is_active']

class SubscriptionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionHistory
        fields = ['id', 'tier', 'action', 'changed_at', 'note']
