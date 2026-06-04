from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import UserStreak, DailyTarget

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_gamification_profiles(sender, instance, created, **kwargs):
    if created:
        UserStreak.objects.create(user=instance)
        DailyTarget.objects.create(user=instance)
