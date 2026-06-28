import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from .models import UserSubscription, SubscriptionPlan, SubscriptionHistory

logger = logging.getLogger(__name__)

class BasePaymentService:
    """Interface cổng thanh toán — có thể mở rộng sau này."""
    def process_payment(self, user, amount: Decimal) -> bool:
        raise NotImplementedError("Payment services must implement process_payment")

class MockPaymentService(BasePaymentService):
    """Giả lập thanh toán luôn thành công."""
    def process_payment(self, user, amount: Decimal) -> bool:
        logger.info(f"Mock Payment processed successfully for user {user.username} with amount {amount}")
        return True

class SubscriptionManager:
    """Lớp điều phối nghiệp vụ Subscription (Nâng cấp/Hạ cấp)."""
    def __init__(self, payment_service: BasePaymentService):
        self.payment_service = payment_service

    def upgrade_tier(self, user, target_tier: str) -> dict:
        """
        Nâng cấp ngay lập tức:
        - Hủy bỏ gói cũ tức thì.
        - Thanh toán toàn bộ giá gói mới.
        - Reset chu kỳ end_date = today + 30 ngày (nếu không phải Premium vĩnh viễn).
        - Nếu target_tier là Premium -> end_date = None (Vĩnh viễn).
        """
        tiers = ['Free', 'Plus', 'Pro', 'Premium']
        if target_tier not in tiers:
            raise ValueError(f"Gói '{target_tier}' không hợp lệ.")

        try:
            plan = SubscriptionPlan.objects.get(tier=target_tier)
        except SubscriptionPlan.DoesNotExist:
            raise ValueError(f"Gói cấu hình '{target_tier}' không tồn tại.")

        sub = getattr(user, 'subscription', None)
        if not sub:
            # Dự phòng nếu chưa có instance subscription (signal post_save chưa tạo)
            sub = UserSubscription.objects.create(user=user, tier='Free')

        if sub.tier == target_tier:
            raise ValueError(f"Bạn đang sử dụng gói {target_tier} rồi.")

        # Kiểm tra xem có thực sự là nâng cấp hay không
        current_idx = tiers.index(sub.tier)
        target_idx = tiers.index(target_tier)
        if target_idx < current_idx:
            raise ValueError("Không thể sử dụng luồng Nâng cấp cho gói thấp hơn. Hãy sử dụng luồng Hạ cấp.")

        # Xử lý thanh toán thông qua Payment Service
        if plan.total_price > 0:
            payment_success = self.payment_service.process_payment(user, plan.total_price)
            if not payment_success:
                raise RuntimeError("Thanh toán không thành công. Vui lòng thử lại.")

        with transaction.atomic():
            locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)
            old_tier = locked_sub.tier

            # Cập nhật thông tin gói mới
            locked_sub.tier = target_tier
            locked_sub.price = plan.price
            locked_sub.vat = plan.vat
            locked_sub.is_active = True
            locked_sub.pending_downgrade_tier = None
            locked_sub.start_date = timezone.now()

            if target_tier == 'Premium':
                locked_sub.end_date = None
            else:
                locked_sub.end_date = timezone.now() + timezone.timedelta(days=30)

            locked_sub.save()

        # Cập nhật instance trong memory tránh stale cache
        user.subscription = locked_sub

        return {
            'status': 'upgraded',
            'old_tier': old_tier,
            'new_tier': target_tier,
            'end_date': locked_sub.end_date
        }

    def request_downgrade(self, user, target_tier: str) -> dict:
        """
        Hạ cấp gói:
        - Nếu gói hiện hành là Premium (Vĩnh viễn): Hạ cấp tức thì (vì không có hạn end_date).
        - Ngược lại: Thiết lập pending_downgrade_tier (Deferred Downgrade), giữ nguyên quyền lợi đến hết kỳ.
        """
        tiers = ['Free', 'Plus', 'Pro', 'Premium']
        if target_tier not in tiers:
            raise ValueError(f"Gói '{target_tier}' không hợp lệ.")

        sub = getattr(user, 'subscription', None)
        if not sub:
            raise ValueError("Người dùng chưa có gói đăng ký nào.")

        current_idx = tiers.index(sub.tier)
        target_idx = tiers.index(target_tier)

        if target_idx >= current_idx:
            raise ValueError("Không thể hạ cấp lên gói cao hơn hoặc bằng gói hiện tại.")

        if sub.tier == 'Premium':
            # Premium hạ cấp -> Thực hiện ngay lập tức
            try:
                plan = SubscriptionPlan.objects.get(tier=target_tier)
            except SubscriptionPlan.DoesNotExist:
                raise ValueError(f"Gói cấu hình '{target_tier}' không tồn tại.")

            with transaction.atomic():
                locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)
                old_tier = locked_sub.tier
                
                locked_sub.tier = target_tier
                locked_sub.price = plan.price
                locked_sub.vat = plan.vat
                locked_sub.pending_downgrade_tier = None
                locked_sub.start_date = timezone.now()

                if target_tier == 'Free':
                    locked_sub.is_active = False
                    locked_sub.end_date = None
                else:
                    locked_sub.is_active = True
                    locked_sub.end_date = timezone.now() + timezone.timedelta(days=30)
                
                locked_sub.save()

            user.subscription = locked_sub
            return {
                'status': 'downgraded_immediately',
                'old_tier': old_tier,
                'new_tier': target_tier,
                'end_date': locked_sub.end_date
            }
        else:
            # Deferred Downgrade: Giữ quyền lợi gói cũ
            with transaction.atomic():
                locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)
                locked_sub.pending_downgrade_tier = target_tier
                locked_sub.save()

            user.subscription = locked_sub
            return {
                'status': 'downgrade_scheduled',
                'old_tier': sub.tier,
                'new_tier': sub.tier,
                'pending_tier': target_tier,
                'end_date': sub.end_date
            }

    def cancel_downgrade(self, user) -> dict:
        """Hủy yêu cầu hạ cấp đang chờ xử lý."""
        sub = getattr(user, 'subscription', None)
        if not sub or not sub.pending_downgrade_tier:
            raise ValueError("Không có yêu cầu hạ cấp nào đang chờ xử lý.")

        with transaction.atomic():
            locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)
            cancelled_tier = locked_sub.pending_downgrade_tier
            locked_sub.pending_downgrade_tier = None
            locked_sub.save()

        user.subscription = locked_sub
        return {
            'status': 'cancelled',
            'cancelled_tier': cancelled_tier,
            'current_tier': locked_sub.tier
        }
