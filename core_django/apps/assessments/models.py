import uuid
from django.db import models
from django.conf import settings


class AssessmentTask(models.Model):
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('zh', 'Chinese'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    QUEUE_CHOICES = [
        ('queue_paid', 'Paid Queue'),
        ('queue_free', 'Free Queue'),
        ('queue_guest', 'Guest Queue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assessments',
        help_text="Nullable — system allows anonymous usage",
    )
    audio_file = models.FileField(upload_to='audio_temp/')
    target_text = models.TextField(blank=True, default='')
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    queue_name = models.CharField(
        max_length=20,
        choices=QUEUE_CHOICES,
        default='queue_guest',
        db_index=True,
        help_text="The physical queue in Redis/Celery that this task is routed to",
    )
    score = models.FloatField(null=True, blank=True)
    result_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.id} - {self.language} - {self.status}"
