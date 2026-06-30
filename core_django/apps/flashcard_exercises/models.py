import uuid
from django.db import models


class FlashcardExercise(models.Model):
    """
    Bài tập FlashCard được AI gen và cache vĩnh viễn.
    Lookup key: (word, lang, exercise_type)
    """
    EXERCISE_TYPES = [
        ('reading', 'Reading Quiz'),      # Tab 2 - Đọc
        ('listening', 'Listening Quiz'),   # Tab 3 - Nghe  
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    word = models.CharField(max_length=255, db_index=True, verbose_name='Từ vựng gốc')
    lang = models.CharField(
        max_length=10, 
        default='zh', 
        choices=[('zh', 'Chinese'), ('en', 'English')],
        verbose_name='Ngôn ngữ'
    )
    exercise_type = models.CharField(max_length=20, choices=EXERCISE_TYPES, verbose_name='Loại bài tập')
    
    # JSON chứa nội dung bài tập
    content = models.JSONField(verbose_name='Nội dung bài tập')
    
    # Audio URL cho tab Nghe (gen bởi tts_service)
    audio_url = models.URLField(blank=True, default='', verbose_name='Audio URL (Listening)')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['word', 'lang']),
            models.Index(fields=['word', 'lang', 'exercise_type']),
        ]
        verbose_name = 'Flashcard Exercise'
        verbose_name_plural = 'Flashcard Exercises'

    def __str__(self):
        return f"{self.word} ({self.lang}) - {self.exercise_type} - {self.id}"


class UserFlashcardHistory(models.Model):
    """
    Lưu lịch sử bài tập FlashCard mà user đã hoàn thành.
    Giới hạn tối đa 10 bản ghi cho mỗi (user, word, lang, exercise_type).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'users.CustomUser', 
        on_delete=models.CASCADE, 
        related_name='flashcard_history'
    )
    exercise = models.ForeignKey(FlashcardExercise, on_delete=models.CASCADE, related_name='user_history')
    word = models.CharField(max_length=255, db_index=True)
    lang = models.CharField(max_length=10, default='zh')
    exercise_type = models.CharField(max_length=20)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'word', 'lang', 'exercise_type']),
        ]
        ordering = ['completed_at']
        verbose_name = 'User Flashcard History'
        verbose_name_plural = 'User Flashcard Histories'

    def __str__(self):
        return f"{self.user.email} - {self.word} ({self.lang}) - {self.exercise_type}"
