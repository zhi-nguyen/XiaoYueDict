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

    def __str__(self) -> str:
        return f"{self.report_type} on {self.content_type} ({self.status})"


class FeatureReport(models.Model):
    """
    Lưu đề xuất tính năng mới hoặc góp ý cải thiện từ người dùng.
    Luồng một chiều: User gửi → Admin đọc → Ghi chú nội bộ → Đánh dấu trạng thái.
    """
    FEATURE_AREA_CHOICES = [
        ('dictionary', 'Tra từ & Học tập'),
        ('speaking', 'Luyện nói'),
        ('writing', 'Luyện viết'),
        ('exam', 'Luyện thi'),
        ('notes', 'Sổ tay'),
        ('translate', 'Dịch thông minh'),
        ('ui_ux', 'Giao diện & Trải nghiệm'),
        ('other', 'Khác'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('reviewing', 'Đang xem xét'),
        ('planned', 'Đã lên kế hoạch'),
        ('implemented', 'Đã triển khai'),
        ('dismissed', 'Bỏ qua'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='feature_reports'
    )
    guest_id = models.CharField(max_length=64, blank=True, db_index=True)
    title = models.CharField(max_length=150)
    description = models.TextField()
    feature_area = models.CharField(max_length=30, choices=FEATURE_AREA_CHOICES, default='other')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reports_featurereport"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.feature_area}] {self.title} ({self.status})"


class SupportRequest(models.Model):
    """
    Lưu yêu cầu hỗ trợ kỹ thuật, thanh toán, tài khoản.
    Guest cần cung cấp email liên hệ để nhận phản hồi.
    Luồng trao đổi đa chiều thông qua TicketComment.
    """
    CATEGORY_CHOICES = [
        ('bug', 'Báo cáo lỗi hệ thống'),
        ('billing', 'Thanh toán & Đăng ký'),
        ('account', 'Tài khoản & Bảo mật'),
        ('other', 'Hỗ trợ khác'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Thấp'),
        ('medium', 'Trung bình'),
        ('high', 'Cao'),
        ('urgent', 'Khẩn cấp'),
    ]

    STATUS_CHOICES = [
        ('open', 'Đang mở'),
        ('in_progress', 'Đang xử lý'),
        ('resolved', 'Đã giải quyết'),
        ('closed', 'Đã đóng'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='support_requests'
    )
    guest_id = models.CharField(max_length=64, blank=True, db_index=True)
    guest_name = models.CharField(max_length=100, blank=True, default='')
    guest_email = models.EmailField(blank=True, default='', db_index=True)

    title = models.CharField(max_length=150)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reports_supportrequest"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.category}] {self.title} ({self.status})"


class TicketComment(models.Model):
    """
    Quản lý luồng trao đổi đa chiều giữa Admin(s) và User trên mỗi SupportRequest.
    Hỗ trợ:
    - Nhiều admin cùng xử lý mà không ghi đè nhau
    - Phân biệt ghi chú nội bộ (is_internal=True) vs phản hồi công khai cho user
    - Lưu trữ lịch sử theo trục thời gian
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        'SupportRequest',
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ticket_comments'
    )
    comment_text = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="True = Ghi chú nội bộ giữa các Admin; False = Công khai cho người dùng"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reports_ticketcomment"
        verbose_name = "Ticket Comment"
        verbose_name_plural = "Ticket Comments"
        ordering = ['created_at']

    def __str__(self) -> str:
        author_name = self.author.username if self.author else "System"
        visibility = "Internal" if self.is_internal else "Public"
        return f"[{visibility}] {author_name} on {self.ticket_id}"
