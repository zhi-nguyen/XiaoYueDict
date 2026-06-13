from django.db import models
from django.conf import settings


class Notebook(models.Model):
    """
    Sổ tay từ vựng — mỗi sổ chỉ cần một tên.
    Người dùng có thể tạo nhiều sổ.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notebooks',
        verbose_name='Người sở hữu',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255, verbose_name='Tên sổ')
    description = models.TextField(blank=True, default='', verbose_name='Mô tả')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Notebook'
        verbose_name_plural = 'Notebooks'

    def __str__(self):
        return self.name

    @property
    def word_count(self):
        return self.words.count()


class Word(models.Model):
    """
    Từ vựng trong sổ tay.
    Bao gồm: từ vựng (hanzi), bính âm (pinyin), nghĩa, ghi chú.
    """
    notebook = models.ForeignKey(
        Notebook,
        on_delete=models.CASCADE,
        related_name='words',
        verbose_name='Sổ tay',
    )
    vocabulary = models.CharField(max_length=255, verbose_name='Từ vựng')
    pinyin = models.CharField(max_length=255, blank=True, default='', verbose_name='Bính âm')
    meaning = models.TextField(blank=True, default='', verbose_name='Nghĩa')
    note = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Word'
        verbose_name_plural = 'Words'

    def __str__(self):
        display = self.vocabulary
        if self.pinyin:
            display += f' ({self.pinyin})'
        if self.meaning:
            display += f' - {self.meaning}'
        return display
