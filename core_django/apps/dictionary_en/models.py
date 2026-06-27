import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField, SearchVector
from django.db.models import Value

class EnWord(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    word = models.CharField(max_length=100, unique=True, db_index=True)
    ipa = models.CharField(max_length=100, blank=True) # Phiên âm quốc tế
    translation_vi = models.TextField(blank=True) # Dịch nghĩa tiếng Việt (fallback)
    definitions = models.JSONField(default=list) # Danh sách định nghĩa
    part_of_speech = models.JSONField(default=list) # Từ loại (Mảng các từ loại, VD: ["noun", "verb"])
    cefr_level = models.CharField(max_length=10, blank=True, db_index=True) # A1, A2, B1, B2, C1, C2
    
    # CEFR Profile details
    core_inventory_1 = models.CharField(max_length=255, blank=True)
    core_inventory_2 = models.CharField(max_length=255, blank=True)
    threshold = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    
    # Prompting & Multimedia
    image_caption = models.TextField(blank=True) # Mô tả hình ảnh tiếng Anh làm Prompt
    audio_url = models.URLField(max_length=500, blank=True)
    image_url = models.URLField(max_length=500, blank=True)

    def save(self, *args, **kwargs):
        if not self.id and self.word:
            # Sinh uuid5 dựa trên word để đảm bảo id là duy nhất và cố định theo từ khóa
            self.id = uuid.uuid5(uuid.NAMESPACE_DNS, self.word)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.word

class EnExample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.ForeignKey(EnWord, on_delete=models.CASCADE, related_name='examples')
    english = models.TextField()
    vietnamese = models.TextField()
    audio_url = models.URLField(max_length=500, blank=True)
    
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [
            GinIndex(fields=['search_vector'], name='enexample_search_vector_gin'),
            GinIndex(fields=['vietnamese'], name='en_matching_vi_trgm_idx', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        return self.english

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        EnExample.objects.filter(pk=self.pk).update(
            search_vector=SearchVector(Value(self.english), config='english')
        )
