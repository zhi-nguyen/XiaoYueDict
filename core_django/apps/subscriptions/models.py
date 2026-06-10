from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone

class SubscriptionPlan(models.Model):
    TIER_CHOICES = [
        ('Free', 'Free'),
        ('Plus', 'Plus'),
        ('Premium', 'Premium'),
        ('Pro', 'Pro'),
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
    TIER_CHOICES = [
        ('Free', 'Free'),
        ('Plus', 'Plus'),
        ('Premium', 'Premium'),
        ('Pro', 'Pro'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='Free')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Giá gốc lưu tại thời điểm thanh toán")
    vat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Tỷ lệ thuế VAT (%) lưu tại thời điểm thanh toán")

    def __str__(self):
        return f"{self.user.username} - {self.tier}"

    def check_validity(self):
        if self.tier != 'Free' and self.end_date and self.end_date < timezone.now():
            self.tier = 'Free'
            self.is_active = False
            self.save()
            return False
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

    def __str__(self):
        return f"Config {self.tier}: {self.mb_per_minute}MB/m, {self.mb_per_hour}MB/h, {self.mb_per_day}MB/d"

