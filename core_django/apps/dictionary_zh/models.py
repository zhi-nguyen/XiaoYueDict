import uuid
from django.db import models

from django.contrib.postgres.indexes import GinIndex

class ZhWord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.CharField(max_length=50, unique=True, db_index=True) # Từ vựng (VD: 爱)
    traditional = models.CharField(max_length=50, blank=True) # Phồn thể
    
    pinyin = models.CharField(max_length=100, db_index=True) # Pinyin có dấu (VD: ài)
    toneless_pinyin = models.CharField(max_length=100, db_index=True) # Pinyin không dấu (VD: ai)
    han_viet = models.CharField(max_length=100, blank=True, db_index=True) # Hán việt
    
    # Dịch nghĩa
    translation_vi = models.TextField()
    translation_en = models.TextField(blank=True)
    
    # Đặc tính ngôn ngữ
    part_of_speech = models.JSONField(default=list) # Array ["verb", "noun"]
    hsk_level = models.CharField(max_length=10, db_index=True) # "1", "2", "7-8-9"
    
    # Thành phần cấu tạo (Sử dụng JSONField cho các mảng)
    radical = models.JSONField(default=list) # Bộ thủ
    stroke_number = models.JSONField(default=list) # Số nét
    components = models.JSONField(default=list) # Thành phần chữ (List of lists)
    
    # Quan hệ & Phân loại
    synonyms = models.JSONField(default=list) # Từ đồng nghĩa
    antonyms = models.JSONField(default=list) # Từ trái nghĩa
    tags = models.JSONField(default=list) # Semantic Tags (VD: ["情感", "喜欢"])
    
    # Thống kê độ phổ biến
    word_frequency = models.FloatField(default=0.0)
    popularity_rank = models.IntegerField(default=0)
    
    # URL file âm thanh (nếu có)
    audio_url = models.URLField(max_length=500, blank=True)

    class Meta:
        indexes = [
            GinIndex(fields=['translation_vi'], name='zhword_trans_vi_gin', opclasses=['gin_trgm_ops']),
            GinIndex(fields=['han_viet'], name='zhword_hanviet_gin', opclasses=['gin_trgm_ops']),
            GinIndex(fields=['toneless_pinyin'], name='zhword_tpinyin_gin', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        return f"{self.word} ({self.pinyin})"

from django.contrib.postgres.search import SearchVectorField, SearchVector
from django.db.models import Value
import jieba

class ZhExample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.ForeignKey(ZhWord, on_delete=models.CASCADE, related_name='examples')
    chinese = models.TextField()
    pinyin = models.TextField()
    vietnamese = models.TextField()
    audio_url = models.URLField(max_length=500, blank=True)
    
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [
            GinIndex(fields=['search_vector'], name='zhexample_search_vector_gin'),
            GinIndex(fields=['vietnamese'], name='zh_matching_vi_trgm_idx', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        return self.chinese

    def save(self, *args, **kwargs):
        # Lưu đối tượng trước để chắc chắn có ID
        super().save(*args, **kwargs)
        
        # Tiền xử lý: Dùng jieba cắt từ tiếng Trung và nối bằng khoảng trắng
        tokenized_chinese = " ".join(jieba.cut(self.chinese))
        
        # Cập nhật trường search_vector bằng query update() để tránh đệ quy save()
        ZhExample.objects.filter(pk=self.pk).update(
            search_vector=SearchVector(Value(tokenized_chinese), config='simple')
        )
