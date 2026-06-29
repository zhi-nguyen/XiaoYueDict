from rest_framework import serializers
from .models import Notebook, Word, PDFExportTask


class WordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Word
        fields = [
            'id', 'notebook', 'vocabulary', 'pinyin',
            'meaning', 'note', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WordCreateSerializer(serializers.ModelSerializer):
    """Serializer dùng khi thêm từ vào sổ (notebook được lấy từ URL)."""
    class Meta:
        model = Word
        fields = ['vocabulary', 'pinyin', 'meaning', 'note']


class NotebookListSerializer(serializers.ModelSerializer):
    """Danh sách sổ tay — kèm số từ."""
    word_count = serializers.SerializerMethodField()
    word_count_annotated = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = ['id', 'name', 'description', 'lang', 'word_count', 'word_count_annotated', 'created_at', 'updated_at']
        read_only_fields = ['id', 'word_count', 'word_count_annotated', 'created_at', 'updated_at']

    def get_word_count(self, obj):
        # If annotated, use the annotated count, otherwise run database count
        val = getattr(obj, 'word_count_annotated', None)
        return val if val is not None else obj.words.count()

    def get_word_count_annotated(self, obj):
        val = getattr(obj, 'word_count_annotated', None)
        return val if val is not None else obj.words.count()


class NotebookDetailSerializer(serializers.ModelSerializer):
    """Chi tiết sổ tay — kèm danh sách từ."""
    words = WordSerializer(many=True, read_only=True)
    word_count = serializers.IntegerField(read_only=True, source='words.count')
    word_count_annotated = serializers.IntegerField(read_only=True, source='words.count')

    class Meta:
        model = Notebook
        fields = ['id', 'name', 'description', 'lang', 'word_count', 'word_count_annotated', 'words', 'created_at', 'updated_at']
        read_only_fields = ['id', 'word_count', 'word_count_annotated', 'created_at', 'updated_at']


class NotebookCreateSerializer(serializers.ModelSerializer):
    """Tạo sổ — chỉ cần tên."""
    class Meta:
        model = Notebook
        fields = ['name', 'description', 'lang']


class PDFExportTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDFExportTask
        fields = [
            'id', 'notebook', 'status', 'queue_name',
            'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'notebook', 'status', 'queue_name', 'error_message', 'created_at', 'updated_at']
