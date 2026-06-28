from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import UserSubscription

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_subscription(sender, instance, created, **kwargs):
    if created:
        UserSubscription.objects.create(user=instance, tier='Free')

from django.db.models.signals import pre_save
from .models import SubscriptionHistory

@receiver(pre_save, sender=UserSubscription)
def log_subscription_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = UserSubscription.objects.get(pk=instance.pk)
            if old_instance.tier != instance.tier:
                action = 'UPGRADE'
                tiers = ['Free', 'Plus', 'Pro', 'Premium']
                try:
                    old_idx = tiers.index(old_instance.tier)
                    new_idx = tiers.index(instance.tier)
                    if new_idx < old_idx:
                        action = 'DOWNGRADE'
                        if instance.tier == 'Free':
                            action = 'CANCEL'
                except ValueError:
                    pass

                SubscriptionHistory.objects.create(
                    user=instance.user,
                    tier=instance.tier,
                    action=action,
                    note=f"Thay đổi từ {old_instance.tier} sang {instance.tier}"
                )
            elif old_instance.pending_downgrade_tier != instance.pending_downgrade_tier:
                if instance.pending_downgrade_tier:
                    action = 'DOWNGRADE' if instance.pending_downgrade_tier != 'Free' else 'CANCEL'
                    note = f"Đã lên lịch hạ cấp từ {instance.tier} xuống {instance.pending_downgrade_tier} vào cuối kỳ."
                    SubscriptionHistory.objects.create(
                        user=instance.user,
                        tier=instance.pending_downgrade_tier,
                        action=action,
                        note=note
                    )
                else:
                    # Hủy yêu cầu hạ cấp
                    SubscriptionHistory.objects.create(
                        user=instance.user,
                        tier=instance.tier,
                        action='RENEW',
                        note=f"Đã hủy yêu cầu hạ cấp xuống {old_instance.pending_downgrade_tier}. Tiếp tục gia hạn gói {instance.tier}."
                    )
            elif old_instance.end_date != instance.end_date and instance.end_date:
                SubscriptionHistory.objects.create(
                    user=instance.user,
                    tier=instance.tier,
                    action='RENEW',
                    note="Gia hạn thời gian sử dụng"
                )
        except UserSubscription.DoesNotExist:
            pass
    else:
        if instance.tier != 'Free':
            SubscriptionHistory.objects.create(
                user=instance.user,
                tier=instance.tier,
                action='UPGRADE',
                note="Khởi tạo gói"
            )


from .models import VolumeLimitConfig
from core_project.ws_utils import get_redis_client

@receiver(post_save, sender=VolumeLimitConfig)
def sync_volume_limit_to_redis(sender, instance, **kwargs):
    r = get_redis_client()
    config_key = f"config:volume:{instance.tier.upper()}"
    r.hset(config_key, mapping={
        'min': instance.mb_per_minute * 1024 * 1024,
        'hr': instance.mb_per_hour * 1024 * 1024,
        'day': instance.mb_per_day * 1024 * 1024
    })

