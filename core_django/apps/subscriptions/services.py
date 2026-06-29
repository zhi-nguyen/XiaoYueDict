import hmac
import hashlib
import logging
import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from .models import UserSubscription, SubscriptionPlan, SubscriptionHistory, PaymentOrder

logger = logging.getLogger(__name__)

# ─── SePay Configuration (dynamic helper functions to support test overrides) ───
def get_sepay_webhook_secret():
    return getattr(settings, 'SEPAY_WEBHOOK_SECRET', '')

def get_sepay_bank_code():
    return getattr(settings, 'SEPAY_BANK_CODE', '')

def get_sepay_account_number():
    return getattr(settings, 'SEPAY_ACCOUNT_NUMBER', '')

def get_sepay_account_name():
    return getattr(settings, 'SEPAY_ACCOUNT_NAME', '')

def get_sepay_order_prefix():
    return getattr(settings, 'SEPAY_ORDER_PREFIX', 'CNEN')

def get_sepay_payment_timeout_minutes():
    try:
        return int(getattr(settings, 'SEPAY_PAYMENT_TIMEOUT_MINUTES', 15))
    except (ValueError, TypeError):
        return 15


class BasePaymentService:
    """Interface cổng thanh toán — có thể mở rộng sau này."""
    def process_payment(self, user, amount: Decimal) -> bool:
        raise NotImplementedError("Payment services must implement process_payment")


class MockPaymentService(BasePaymentService):
    """Giả lập thanh toán luôn thành công — chỉ dùng cho automated tests."""
    def process_payment(self, user, amount: Decimal) -> bool:
        logger.info(f"Mock Payment processed successfully for user {user.username} with amount {amount}")
        return True


class SePayPaymentService:
    """
    Xử lý thanh toán thực qua SePay VietQR Webhook.

    Flow:
    1. User yêu cầu nâng cấp → create_payment_order() → trả QR data
    2. User quét QR, chuyển khoản thật
    3. SePay gửi webhook (IPN) → handle_webhook() → xác nhận + nâng cấp
    """

    def create_payment_order(self, user, plan: SubscriptionPlan, target_tier: str) -> PaymentOrder:
        """
        Tạo đơn thanh toán mới với mã order_code unique.
        Huỷ tất cả đơn PENDING cũ của user cho cùng tier.
        """
        # Huỷ các đơn PENDING cũ của user (tránh trùng lặp)
        PaymentOrder.objects.filter(
            user=user,
            status='PENDING'
        ).update(status='EXPIRED')

        order_code = self._generate_order_code()
        transfer_content = f"{get_sepay_order_prefix()} {order_code}"
        amount = int(plan.total_price)  # VNĐ, làm tròn

        order = PaymentOrder.objects.create(
            user=user,
            target_tier=target_tier,
            amount=amount,
            order_code=order_code,
            transfer_content=transfer_content,
            expires_at=timezone.now() + timezone.timedelta(minutes=get_sepay_payment_timeout_minutes()),
        )

        logger.info(
            f"Payment order created: {order_code} for user {user.username}, "
            f"tier={target_tier}, amount={amount}"
        )
        return order

    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature: str, timestamp: str = None) -> bool:
        """
        Xác thực chữ ký HMAC-SHA256 từ SePay.
        SePay gửi signature trong header, ta cần so khớp với hash tính từ body + secret.
        Nếu có timestamp, SePay ký theo định dạng: {timestamp}.{payload_body}
        """
        secret = get_sepay_webhook_secret()
        if not secret:
            logger.error("SEPAY_WEBHOOK_SECRET is not configured!")
            return False

        if timestamp:
            msg = f"{timestamp}.".encode('utf-8') + payload_body
        else:
            msg = payload_body

        expected = hmac.new(
            secret.encode('utf-8'),
            msg,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def handle_webhook(self, payload: dict) -> dict:
        """
        Xử lý IPN callback từ SePay.

        Returns:
            dict: {'success': True/False, 'message': str}
        """
        # Chỉ xử lý giao dịch tiền vào (credit)
        transfer_type = payload.get('transferType', '')
        if transfer_type != 'in':
            logger.info(f"Ignoring non-credit transaction: {transfer_type}")
            return {'success': True, 'message': 'Ignored non-credit transaction'}

        content = payload.get('content', '').strip()
        amount = payload.get('transferAmount', 0)
        transaction_id = str(payload.get('id', ''))
        reference_code = payload.get('referenceCode', '')

        # Trích xuất order_code từ nội dung chuyển khoản
        order_code = self._extract_order_code(content)
        if not order_code:
            logger.warning(f"Could not extract order code from content: '{content}'")
            return {'success': True, 'message': 'No matching order code found'}

        # Tìm và xử lý PaymentOrder trong transaction để dùng select_for_update()
        with transaction.atomic():
            try:
                order = PaymentOrder.objects.select_for_update().get(order_code=order_code)
            except PaymentOrder.DoesNotExist:
                logger.warning(f"PaymentOrder not found for order_code: {order_code}")
                return {'success': True, 'message': 'Order not found'}

            # Idempotency: nếu đã PAID rồi thì bỏ qua
            if order.status == 'PAID':
                logger.info(f"Order {order_code} already paid, ignoring duplicate webhook")
                return {'success': True, 'message': 'Already processed'}

            # Kiểm tra hết hạn
            if order.is_expired:
                logger.warning(f"Order {order_code} has expired")
                order.status = 'EXPIRED'
                order.save(update_fields=['status'])
                return {'success': True, 'message': 'Order expired'}

            # Kiểm tra số tiền khớp
            if int(amount) < int(order.amount):
                logger.warning(
                    f"Amount mismatch for order {order_code}: "
                    f"expected={order.amount}, received={amount}"
                )
                return {'success': True, 'message': 'Amount mismatch'}

            # ─── Thanh toán hợp lệ → Nâng cấp tier ───
            # Cập nhật PaymentOrder
            order.status = 'PAID'
            order.paid_at = timezone.now()
            order.sepay_transaction_id = transaction_id
            order.bank_reference = reference_code
            order.save(update_fields=[
                'status', 'paid_at', 'sepay_transaction_id', 'bank_reference'
            ])

            # Nâng cấp subscription
            self._upgrade_user_subscription(order)

        logger.info(
            f"Payment confirmed for order {order_code}: "
            f"user={order.user.username}, tier={order.target_tier}, amount={amount}"
        )
        return {'success': True, 'message': 'Payment processed successfully'}


    def generate_qr_data(self, order: PaymentOrder) -> dict:
        """
        Sinh thông tin QR VietQR cho client hiển thị.
        Sử dụng VietQR URL scheme chuẩn: https://img.vietqr.io/image/
        """
        bank_code = get_sepay_bank_code()
        account_number = get_sepay_account_number()
        account_name = get_sepay_account_name()

        # VietQR image URL format:
        # https://img.vietqr.io/image/{bankCode}-{accountNumber}-<template>.png
        # ?amount={amount}&addInfo={content}&accountName={name}
        qr_url = (
            f"https://img.vietqr.io/image/"
            f"{bank_code}-{account_number}-compact2.png"
            f"?amount={int(order.amount)}"
            f"&addInfo={order.transfer_content}"
            f"&accountName={account_name}"
        )

        return {
            'qr_url': qr_url,
            'bank_code': bank_code,
            'account_number': account_number,
            'account_name': account_name,
            'amount': int(order.amount),
            'transfer_content': order.transfer_content,
            'order_code': order.order_code,
            'order_id': str(order.id),
            'expires_at': order.expires_at.isoformat(),
        }

    def _upgrade_user_subscription(self, order: PaymentOrder):
        """Nâng cấp subscription tier sau khi thanh toán thành công."""
        user = order.user
        target_tier = order.target_tier

        try:
            plan = SubscriptionPlan.objects.get(tier=target_tier)
        except SubscriptionPlan.DoesNotExist:
            logger.error(f"SubscriptionPlan '{target_tier}' does not exist!")
            raise

        sub = getattr(user, 'subscription', None)
        if not sub:
            sub = UserSubscription.objects.create(user=user, tier='Free')

        locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)

        locked_sub.tier = target_tier
        locked_sub.price = plan.price
        locked_sub.vat = plan.vat
        locked_sub.is_active = True
        locked_sub.pending_downgrade_tier = None  # Huỷ downgrade nếu đang chờ
        locked_sub.start_date = timezone.now()

        if target_tier == 'Premium':
            locked_sub.end_date = None  # Vĩnh viễn
        else:
            locked_sub.end_date = timezone.now() + timezone.timedelta(days=30)

        locked_sub.save()

        # Đồng bộ instance trong memory
        user.subscription = locked_sub

    @staticmethod
    def _generate_order_code() -> str:
        """Sinh mã đơn hàng unique, dạng: ORDxxxxxxxx (8 ký tự hex)."""
        return f"ORD{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _extract_order_code(content: str) -> str:
        """
        Trích xuất order_code từ nội dung chuyển khoản.
        Nội dung mong đợi: 'CNEN ORDxxxxxxxx' hoặc chứa 'ORDxxxxxxxx' ở đâu đó.
        Ngân hàng có thể thêm prefix/suffix, nên tìm bằng regex.
        """
        import re
        match = re.search(r'(ORD[A-Z0-9]{8})', content.upper())
        if match:
            return match.group(1)
        return ''


class SubscriptionManager:
    """Lớp điều phối nghiệp vụ Subscription (Nâng cấp/Hạ cấp)."""
    def __init__(self, payment_service=None):
        self.payment_service = payment_service or SePayPaymentService()

    def initiate_upgrade(self, user, target_tier: str) -> dict:
        """
        Khởi tạo luồng nâng cấp:
        - Validate tier hợp lệ + là nâng cấp thực sự.
        - Tạo PaymentOrder (PENDING).
        - Trả về QR data cho client hiển thị.

        Nếu đang có pending downgrade, sẽ được huỷ khi thanh toán thành công.
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
            sub = UserSubscription.objects.create(user=user, tier='Free')

        if sub.tier == target_tier:
            raise ValueError(f"Bạn đang sử dụng gói {target_tier} rồi.")

        current_idx = tiers.index(sub.tier)
        target_idx = tiers.index(target_tier)
        if target_idx < current_idx:
            raise ValueError("Không thể sử dụng luồng Nâng cấp cho gói thấp hơn. Hãy sử dụng luồng Hạ cấp.")

        if plan.total_price <= 0:
            raise ValueError("Gói miễn phí không cần thanh toán.")

        # Tạo đơn thanh toán
        if not isinstance(self.payment_service, SePayPaymentService):
            raise RuntimeError("Payment service không hỗ trợ tạo đơn thanh toán.")

        order = self.payment_service.create_payment_order(user, plan, target_tier)
        qr_data = self.payment_service.generate_qr_data(order)

        return {
            'status': 'payment_pending',
            'message': 'Vui lòng quét mã QR để thanh toán.',
            'payment': qr_data,
        }

    def upgrade_tier(self, user, target_tier: str) -> dict:
        """
        Nâng cấp ngay lập tức (dành cho Mock / Admin / Test):
        - Hủy bỏ gói cũ tức thì.
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
            sub = UserSubscription.objects.create(user=user, tier='Free')

        if sub.tier == target_tier:
            raise ValueError(f"Bạn đang sử dụng gói {target_tier} rồi.")

        current_idx = tiers.index(sub.tier)
        target_idx = tiers.index(target_tier)
        if target_idx < current_idx:
            raise ValueError("Không thể sử dụng luồng Nâng cấp cho gói thấp hơn. Hãy sử dụng luồng Hạ cấp.")

        # Xử lý thanh toán thông qua Payment Service nếu có
        if plan.total_price > 0:
            if hasattr(self.payment_service, 'process_payment'):
                payment_success = self.payment_service.process_payment(user, plan.total_price)
                if not payment_success:
                    raise RuntimeError("Thanh toán không thành công. Vui lòng thử lại.")
            else:
                raise RuntimeError("Payment service không hỗ trợ nâng cấp đồng bộ trực tiếp.")

        with transaction.atomic():
            locked_sub = UserSubscription.objects.select_for_update().get(pk=sub.pk)
            old_tier = locked_sub.tier

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
            # Deferred Downgrade: Giữ quyền lợi gói cũ đến hết kỳ
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
