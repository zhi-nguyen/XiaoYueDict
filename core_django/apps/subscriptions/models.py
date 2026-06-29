import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone

class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TIER_CHOICES = [
        ('Free', 'Free'),
        ('Plus', 'Plus'),
        ('Pro', 'Pro'),
        ('Premium', 'Premium'),
    ]
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Giá gốc của gói")
    vat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Tỷ lệ thuế VAT (%)")
    description = models.TextField(blank=True, default='', help_text="Mô tả quyền lợi của gói")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Plan {self.tier} - {self.price} (VAT: {self.vat}%)"

    @property
    def total_price(self):
        """
        Tính tổng chi phí đã bao gồm thuế VAT và làm tròn chuẩn tài chính đến 2 chữ số thập phân.
        """
        if not self.price:
            return Decimal('0.00')
        total = self.price * (Decimal('1') + (self.vat / Decimal('100')))
        return total.quantize(Decimal('0.01'))


class UserSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TIER_CHOICES = [
        ('Free', 'Free'),
        ('Plus', 'Plus'),
        ('Pro', 'Pro'),
        ('Premium', 'Premium'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='Free')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Giá gốc lưu tại thời điểm thanh toán")
    vat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Tỷ lệ thuế VAT (%) lưu tại thời điểm thanh toán")
    pending_downgrade_tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        null=True,
        blank=True,
        help_text="Gói sẽ chuyển xuống khi hết hạn end_date"
    )

    def __str__(self):
        return f"{self.user.username} - {self.tier}"

    def check_validity(self):
        if self.tier != 'Free' and self.tier != 'Premium' and self.end_date and self.end_date < timezone.now():
            from django.db import transaction
            with transaction.atomic():
                # Thực hiện khóa hàng PostgreSQL bằng QuerySet thông qua select_for_update()
                locked_sub = UserSubscription.objects.select_for_update().get(pk=self.pk)
                if locked_sub.tier != 'Free' and locked_sub.tier != 'Premium' and locked_sub.end_date and locked_sub.end_date < timezone.now():
                    if locked_sub.pending_downgrade_tier:
                        new_tier = locked_sub.pending_downgrade_tier
                        locked_sub.pending_downgrade_tier = None
                        if new_tier == 'Free':
                            locked_sub.tier = 'Free'
                            locked_sub.is_active = False
                            locked_sub.end_date = None
                        else:
                            # Mock payment success for auto-renew to the scheduled tier
                            locked_sub.tier = new_tier
                            locked_sub.is_active = True
                            # Set price & vat based on the new plan
                            try:
                                plan = SubscriptionPlan.objects.get(tier=new_tier)
                                locked_sub.price = plan.price
                                locked_sub.vat = plan.vat
                            except SubscriptionPlan.DoesNotExist:
                                pass
                            locked_sub.end_date = locked_sub.end_date + timezone.timedelta(days=30)
                    else:
                        locked_sub.tier = 'Free'
                        locked_sub.is_active = False
                        locked_sub.end_date = None

                    locked_sub.save()
                    
                    # Đồng bộ hóa lại trạng thái instance hiện tại
                    self.tier = locked_sub.tier
                    self.is_active = locked_sub.is_active
                    self.end_date = locked_sub.end_date
                    self.pending_downgrade_tier = locked_sub.pending_downgrade_tier
                    self.price = locked_sub.price
                    self.vat = locked_sub.vat
                    return self.is_active
        return True

    @property
    def total_price(self):
        """
        Tính tổng chi phí đã bao gồm thuế VAT và làm tròn chuẩn tài chính đến 2 chữ số thập phân.
        """
        if not self.price:
            return Decimal('0.00')
        total = self.price * (Decimal('1') + (self.vat / Decimal('100')))
        return total.quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        # Tự động sao chép giá gốc và VAT từ SubscriptionPlan master nếu chúng chưa được thiết lập (hoặc bằng 0)
        if (self.price == Decimal('0.00') or self.vat == Decimal('0.00')) and self.tier:
            try:
                plan = SubscriptionPlan.objects.get(tier=self.tier)
                if self.price == Decimal('0.00'):
                    self.price = plan.price
                if self.vat == Decimal('0.00'):
                    self.vat = plan.vat
            except SubscriptionPlan.DoesNotExist:
                pass
        super().save(*args, **kwargs)


class SubscriptionHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ACTION_CHOICES = [
        ('UPGRADE', 'Nâng cấp'),
        ('RENEW', 'Gia hạn'),
        ('DOWNGRADE', 'Hạ cấp'),
        ('CANCEL', 'Hủy gói'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription_logs')
    tier = models.CharField(max_length=20) # Free, Plus, Premium, Pro
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.action} - {self.tier}"


class VolumeLimitConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TIER_CHOICES = [
        ('Guest', 'Guest'),
        ('Free', 'Free'),
        ('Plus', 'Plus'),
        ('Premium', 'Premium'),
        ('Pro', 'Pro'),
    ]
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    mb_per_minute = models.PositiveIntegerField(default=2)
    mb_per_hour = models.PositiveIntegerField(default=20)
    mb_per_day = models.PositiveIntegerField(default=100)
    pdf_daily_limit = models.PositiveIntegerField(default=2, help_text="Số lần xuất PDF tối đa mỗi ngày")
    pdf_word_limit = models.PositiveIntegerField(default=10, help_text="Số từ vựng tối đa mỗi file PDF")

    def __str__(self):
        return f"Config {self.tier}: {self.mb_per_minute}MB/m, {self.mb_per_hour}MB/h, {self.mb_per_day}MB/d, PDF: {self.pdf_daily_limit} times/day, {self.pdf_word_limit} words/file"


class PaymentOrder(models.Model):
    """Đơn thanh toán — theo dõi lifecycle từ PENDING → PAID/EXPIRED/FAILED."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    STATUS_CHOICES = [
        ('PENDING', 'Chờ thanh toán'),
        ('PAID', 'Đã thanh toán'),
        ('EXPIRED', 'Hết hạn'),
        ('FAILED', 'Thất bại'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_orders'
    )
    target_tier = models.CharField(max_length=20, help_text="Gói muốn nâng cấp lên")
    amount = models.DecimalField(
        max_digits=12, decimal_places=0,
        help_text="Số tiền cần thanh toán (VNĐ, không lẻ)"
    )
    order_code = models.CharField(
        max_length=50, unique=True, db_index=True,
        help_text="Mã đơn hàng unique, VD: CNEN-abc12345"
    )
    transfer_content = models.CharField(
        max_length=100,
        help_text="Nội dung chuyển khoản đầy đủ user cần ghi"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='PENDING'
    )

    # SePay transaction data (populated by webhook)
    sepay_transaction_id = models.CharField(max_length=100, blank=True, default='')
    bank_reference = models.CharField(max_length=100, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Thời điểm đơn hàng hết hạn nếu chưa thanh toán")
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_code} - {self.user.username} - {self.status}"

    @property
    def is_expired(self):
        return self.status == 'PENDING' and timezone.now() > self.expires_at

