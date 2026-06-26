import uuid
from django.db import models
from django.conf import settings


class Notebook(models.Model):
    """
    Sổ tay từ vựng — mỗi sổ chỉ cần một tên.
    Người dùng có thể tạo nhiều sổ.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    lang = models.CharField(
        max_length=10,
        default='zh',
        choices=[('zh', 'Chinese'), ('en', 'English')],
        verbose_name='Ngôn ngữ'
    )
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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


class PDFExportTask(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    QUEUE_CHOICES = [
        ('queue_paid', 'Paid Queue'),
        ('queue_free', 'Free Queue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pdf_export_tasks'
    )
    notebook = models.ForeignKey(
        Notebook,
        on_delete=models.CASCADE,
        related_name='pdf_export_tasks'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    queue_name = models.CharField(
        max_length=20,
        choices=QUEUE_CHOICES,
        default='queue_free',
        db_index=True
    )
    pdf_file = models.FileField(upload_to='pdf_exports/', null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.id} - {self.notebook.name} - {self.status}"
