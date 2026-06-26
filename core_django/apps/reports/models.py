import uuid
from django.db import models
from django.conf import settings

class ContentReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('image', 'Ảnh sai/không phù hợp'),
        ('translation', 'Bản dịch sai'),
        ('pinyin', 'Pinyin/IPA sai'),
        ('example', 'Ví dụ sai'),
        ('exam_question', 'Câu hỏi thi sai'),
        ('audio', 'Audio sai/hỏng'),
        ('other', 'Lỗi khác'),
    ]

    CONTENT_TYPE_CHOICES = [
        ('zh_word', 'ZhWord'),
        ('en_word', 'EnWord'),
        ('zh_example', 'ZhExample'),
        ('en_example', 'EnExample'),
        ('exam_question', 'Exam Question'),
        ('exam_option', 'Exam Option'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('reviewing', 'Đang xem xét'),
        ('resolved', 'Đã sửa'),
        ('dismissed', 'Bỏ qua'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    object_id = models.CharField(max_length=64, db_index=True)
    
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='content_reports'
    )
    guest_id = models.CharField(max_length=64, blank=True, db_index=True)
    
    reason = models.TextField(blank=True)
    suggested_correction = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reports_contentreport"
        ordering = ["-created_at"]
        constraints = [
            # Ràng buộc dành cho người dùng đã đăng nhập (Authenticated User)
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'report_type', 'reporter'],
                condition=models.Q(reporter__isnull=False),
                name='unique_authenticated_user_report'
            ),
            # Ràng buộc dành cho người dùng ẩn danh (Guest)
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'report_type', 'guest_id'],
                condition=models.Q(reporter__isnull=True) & ~models.Q(guest_id=''),
                name='unique_guest_user_report'
            )
        ]

    def __str__(self):
        return f"{self.report_type} on {self.content_type} ({self.status})"
