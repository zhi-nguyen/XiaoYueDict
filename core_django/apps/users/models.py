import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bio = models.TextField(blank=True, null=True, help_text="User's short biography")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    firebase_uid = models.CharField(max_length=128, unique=True, null=True, blank=True)

    def __str__(self):
        return self.username

