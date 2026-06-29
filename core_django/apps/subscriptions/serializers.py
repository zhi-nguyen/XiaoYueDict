from rest_framework import serializers
from .models import UserSubscription, SubscriptionHistory, SubscriptionPlan, PaymentOrder

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'tier', 'price', 'vat', 'total_price', 'description']

class UserSubscriptionSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = UserSubscription
        fields = ['tier', 'start_date', 'end_date', 'is_active', 'price', 'vat', 'total_price', 'pending_downgrade_tier']

class SubscriptionRegisterSerializer(serializers.Serializer):
    tier = serializers.ChoiceField(choices=UserSubscription.TIER_CHOICES)

class SubscriptionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionHistory
        fields = ['id', 'tier', 'action', 'changed_at', 'note']

class PaymentOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = [
            'id', 'target_tier', 'amount', 'order_code',
            'transfer_content', 'status',
            'created_at', 'expires_at', 'paid_at',
        ]
        read_only_fields = fields

