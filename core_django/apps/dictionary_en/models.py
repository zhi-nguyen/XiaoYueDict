import uuid
from django.db import models

class EnWord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.CharField(max_length=100, unique=True, db_index=True)
    ipa = models.CharField(max_length=100, blank=True) # Phiên âm quốc tế
    translation_vi = models.TextField()
    part_of_speech = models.JSONField(default=list)
    cefr_level = models.CharField(max_length=10, blank=True, db_index=True) # A1, A2, B1...
    audio_url = models.URLField(max_length=500, blank=True)
    
    def __str__(self):
        return self.word

class EnExample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.ForeignKey(EnWord, on_delete=models.CASCADE, related_name='examples')
    english = models.TextField()
    vietnamese = models.TextField()
    audio_url = models.URLField(max_length=500, blank=True)
