from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Persistent notification storage — ensures no notification is lost
    when user is offline. Redis Pub/Sub is fire-and-forget, so we
    always save to DB first, then publish to WebSocket.
    """

    NOTIFICATION_TYPES = [
        ('score_complete', 'Score Complete'),
        ('score_failed', 'Score Failed'),
        ('streak_update', 'Streak Update'),
        ('subscription_change', 'Subscription Change'),
        ('achievement', 'Achievement'),
        ('system', 'System Message'),
        ('pdf_complete', 'PDF Export Complete'),
        ('pdf_failed', 'PDF Export Failed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.user.username}"
