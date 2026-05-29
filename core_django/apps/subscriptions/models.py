from django.db import models
from django.conf import settings
from django.utils import timezone

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

    def __str__(self):
        return f"{self.user.username} - {self.tier}"

    def check_validity(self):
        if self.tier != 'Free' and self.end_date and self.end_date < timezone.now():
            self.tier = 'Free'
            self.is_active = False
            self.save()
            return False
        return True

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
