from django.db import models


class Exam(models.Model):
    """
    Bài thi HSK - tương ứng exam_metadata + exam_settings trong JSON.
    Ví dụ: "Đề thi thử HSK 1 Mới (Tiêu chuẩn 2026)"
    """
    exam_id = models.CharField(max_length=100, unique=True, help_text="ID duy nhất, VD: HSK1_NEW_UUID_001")
    exam_name = models.CharField(max_length=500, help_text="Tên bài thi")
    exam_version = models.CharField(max_length=20, default="1.0")
    level = models.CharField(max_length=20, help_text="VD: HSK 1, HSK 2, ...")
    total_questions = models.IntegerField(default=0)
    total_time_minutes = models.IntegerField(default=0, help_text="Thời gian thi (phút)")
    total_score = models.IntegerField(default=0, help_text="Tổng điểm tối đa")
    passing_score = models.IntegerField(default=0, help_text="Điểm đạt")

    # exam_settings
    allow_resume = models.BooleanField(default=True, help_text="Cho phép tiếp tục thi")
    max_attempts = models.IntegerField(default=-1, help_text="-1 = không giới hạn")
    shuffle_questions = models.BooleanField(default=False)
    shuffle_options = models.BooleanField(default=False)
    show_explanation_after = models.CharField(
        max_length=50,
        default="exam_submitted",
        help_text="Thời điểm hiển thị giải thích: exam_submitted, each_question, never"
    )

    status = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exams_exam"
        ordering = ["level", "exam_id"]

    def __str__(self):
        return f"{self.level} - {self.exam_name}"


class Section(models.Model):
    """
    Phần thi - tương ứng sections[] trong JSON.
    Ví dụ: Listening Part 1, Listening Part 2, Reading Part 1, ...
    """
    SECTION_NAME_CHOICES = [
        ("Listening", "Listening"),
        ("Reading", "Reading"),
        ("Writing", "Writing"),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    section_id = models.CharField(max_length=100, help_text="VD: sec_listening_01")
    section_name = models.CharField(max_length=50, choices=SECTION_NAME_CHOICES, help_text="Listening / Reading / Writing")
    part_number = models.IntegerField(help_text="Số thứ tự phần trong kỹ năng")
    instruction = models.TextField(blank=True, default="", help_text="Hướng dẫn bằng tiếng Trung, VD: 第一部分：听录音，判断对错")
    section_audio_url = models.URLField(max_length=500, blank=True, default="", help_text="URL audio chung cho cả section")
    ordering = models.IntegerField(default=0, help_text="Thứ tự hiển thị")

    class Meta:
        db_table = "exams_section"
        ordering = ["exam", "ordering", "part_number"]
        unique_together = [["exam", "section_id"]]

    def __str__(self):
        return f"{self.exam.level} | {self.section_name} Part {self.part_number}"


class Question(models.Model):
    """
    Câu hỏi - tương ứng questions[] trong JSON.
    """
    QUESTION_TYPE_CHOICES = [
        ("true_false", "True/False - Đúng Sai"),
        ("multiple_choice", "Multiple Choice - Trắc nghiệm"),
        ("fill_blank", "Fill in Blank - Điền từ"),
        ("matching", "Matching - Nối"),
        ("ordering", "Ordering - Sắp xếp"),
    ]

    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="questions")
    question_id = models.CharField(max_length=100, help_text="VD: q_listen_001")
    question_type = models.CharField(max_length=30, choices=QUESTION_TYPE_CHOICES)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="easy")
    points = models.IntegerField(default=5, help_text="Điểm cho câu hỏi này")
    tags = models.JSONField(default=list, blank=True, help_text='VD: ["listening", "vocabulary", "noun"]')

    # Audio
    audio_url = models.URLField(max_length=500, blank=True, default="", help_text="URL file audio riêng cho câu hỏi")
    audio_start_time = models.CharField(max_length=20, blank=True, default="", help_text="Thời điểm bắt đầu trong audio chung (VD: 00:01:30)")
    audio_end_time = models.CharField(max_length=20, blank=True, default="", help_text="Thời điểm kết thúc trong audio chung")
    audio_script = models.TextField(blank=True, default="", help_text="Nội dung đọc, VD: 医院。 (Yīyuàn)")

    # Content
    question_text = models.TextField(blank=True, default="", help_text="Câu hỏi hiển thị, VD: 小猫在哪儿？")
    image_url = models.URLField(max_length=500, blank=True, default="", help_text="URL hình ảnh đề bài")
    image_description = models.TextField(blank=True, default="", help_text="Mô tả hình ảnh, VD: A hospital building.")

    # Answer
    correct_answer = models.CharField(max_length=50, help_text="ID đáp án đúng, VD: opt_True, opt_A")
    explanation = models.TextField(blank=True, default="", help_text="Giải thích đáp án")

    ordering = models.IntegerField(default=0)

    class Meta:
        db_table = "exams_question"
        ordering = ["section", "ordering"]
        unique_together = [["section", "question_id"]]

    def __str__(self):
        return f"{self.question_id} ({self.question_type})"


class Option(models.Model):
    """
    Đáp án/Lựa chọn - tương ứng options[] trong JSON.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    option_id = models.CharField(max_length=50, help_text="VD: opt_True, opt_A, opt_B, opt_C")
    text = models.TextField(blank=True, default="", help_text="Nội dung text, VD: 椅子下面")
    image_url = models.URLField(max_length=500, blank=True, default="", help_text="URL hình ảnh option")
    image_description = models.TextField(blank=True, default="", help_text="Mô tả hình ảnh option")
    ordering = models.IntegerField(default=0)

    class Meta:
        db_table = "exams_option"
        ordering = ["question", "ordering"]
        unique_together = [["question", "option_id"]]

    def __str__(self):
        display = self.text or self.image_description or self.option_id
        return f"{self.option_id}: {display[:50]}"
