from django.db import models


class ZhEnMapping(models.Model):
    """
    Bảng trung gian bắc cầu Cross-Language Prompt.
    
    Lưu trữ từ khóa tiếng Anh và mô tả hình ảnh (Image Caption)
    từ dữ liệu HSK 1-9, phục vụ cho quá trình xây dựng Prompt 
    gửi đến mô hình AI tạo ảnh (Generative AI).
    """
    zh_word = models.ForeignKey(
        'dictionary_zh.ZhWord',
        on_delete=models.CASCADE,
        related_name='en_mappings',
        help_text="Từ vựng tiếng Trung gốc"
    )
    en_word = models.ForeignKey(
        'dictionary_en.EnWord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='zh_mappings',
        help_text="Từ vựng tiếng Anh tương ứng (nullable nếu chưa nạp vào DB)"
    )
    image_caption = models.TextField(
        blank=True,
        help_text="Mô tả hình ảnh tiếng Anh làm Prompt cho AI sinh ảnh (image caption)"
    )

    class Meta:
        indexes = [
            models.Index(fields=['zh_word']),
            models.Index(fields=['en_word']),
        ]
        unique_together = ('zh_word', 'en_word')
        verbose_name = 'ZH-EN Mapping'
        verbose_name_plural = 'ZH-EN Mappings'

    def __str__(self):
        return f"{self.zh_word} → {self.en_word}"
