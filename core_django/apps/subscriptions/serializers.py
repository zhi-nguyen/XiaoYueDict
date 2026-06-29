from rest_framework import serializers
from .models import UserSubscription, SubscriptionHistory, SubscriptionPlan, PaymentOrder, VolumeLimitConfig

class VolumeLimitConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = VolumeLimitConfig
        fields = ['mb_per_minute', 'mb_per_hour', 'mb_per_day', 'pdf_daily_limit', 'pdf_word_limit']

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()
    limits = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'tier', 'price', 'vat', 'total_price', 'description', 'limits']

    def get_limits(self, obj):
        config = VolumeLimitConfig.objects.filter(tier=obj.tier).first()
        if config:
            return VolumeLimitConfigSerializer(config).data
        return None

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

