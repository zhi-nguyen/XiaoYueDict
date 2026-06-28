from rest_framework import serializers
from .models import ContentReport, FeatureReport, SupportRequest, TicketComment

# Import các model từ hệ thống để validate động
from apps.dictionary_zh.models import ZhWord, ZhExample
from apps.dictionary_en.models import EnWord, EnExample
from apps.exams.models import Question, Option

MODEL_MAPPING = {
    'zh_word': ZhWord,
    'en_word': EnWord,
    'zh_example': ZhExample,
    'en_example': EnExample,
    'exam_question': Question,
    'exam_option': Option,
}

class ContentReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentReport
        fields = [
            'id', 'report_type', 'content_type', 'object_id', 
            'guest_id', 'reason', 'suggested_correction'
        ]
        extra_kwargs = {
            'guest_id': {'required': False, 'allow_blank': True}
        }

    def validate(self, data):
        content_type = data.get('content_type')
        object_id = data.get('object_id')
        
        target_model = MODEL_MAPPING.get(content_type)
        if not target_model:
            raise serializers.ValidationError({"content_type": "Content type không hợp lệ."})

        from django.db import models as django_models
        pk_field = target_model._meta.pk
        cleaned_id = object_id
        
        if isinstance(pk_field, (django_models.AutoField, django_models.BigAutoField, django_models.IntegerField)):
            try:
                cleaned_id = int(object_id)
            except ValueError:
                raise serializers.ValidationError({
                    "object_id": f"ID cung cấp phải là số nguyên cho danh mục {content_type}."
                })
            
        if not target_model.objects.filter(id=cleaned_id).exists():
            raise serializers.ValidationError({
                "object_id": f"Không tìm thấy đối tượng với ID đã cung cấp trong danh mục {content_type}."
            })
            
        # Kiểm tra trùng lặp thủ công trước khi lưu để đưa ra thông báo lỗi thân thiện (409 Conflict)
        request = self.context.get('request')
        user = request.user if request else None
        report_type = data.get('report_type')
        guest_id = data.get('guest_id', '')

        if user and user.is_authenticated:
            exists = ContentReport.objects.filter(
                content_type=content_type,
                object_id=object_id,
                report_type=report_type,
                reporter=user
            ).exists()
        else:
            exists = False
            if guest_id:
                exists = ContentReport.objects.filter(
                    content_type=content_type,
                    object_id=object_id,
                    report_type=report_type,
                    reporter__isnull=True,
                    guest_id=guest_id
                ).exists()

        if exists:
            raise serializers.ValidationError(
                "Bạn đã gửi báo cáo cho nội dung này trước đó rồi.",
                code='duplicate'
            )

        return data


class FeatureReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureReport
        fields = ['id', 'title', 'description', 'feature_area', 'guest_id']
        extra_kwargs = {
            'guest_id': {'required': False, 'allow_blank': True},
        }

    def validate_title(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Tiêu đề không được để trống.")
        return value.strip()

    def validate_description(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Mô tả chi tiết không được để trống.")
        return value.strip()


class FeatureReportListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureReport
        fields = ['id', 'title', 'feature_area', 'status', 'created_at']


class SupportRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportRequest
        fields = [
            'id', 'title', 'description', 'category',
            'guest_id', 'guest_name', 'guest_email',
        ]
        extra_kwargs = {
            'guest_id': {'required': False, 'allow_blank': True},
            'guest_name': {'required': False, 'allow_blank': True},
            'guest_email': {'required': False, 'allow_blank': True},
        }

    def validate_title(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Tiêu đề không được để trống.")
        return value.strip()

    def validate_description(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Mô tả chi tiết không được để trống.")
        return value.strip()

    def validate(self, data: dict) -> dict:
        request = self.context.get('request')
        user = request.user if request else None

        # Guest phải cung cấp email hợp lệ để nhận phản hồi
        if not user or not user.is_authenticated:
            guest_email = data.get('guest_email', '').strip()
            if not guest_email:
                raise serializers.ValidationError({
                    "guest_email": "Vui lòng cung cấp email liên hệ để nhận phản hồi từ hệ thống."
                })

        return data


class SupportRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportRequest
        fields = ['id', 'title', 'category', 'priority', 'status', 'created_at']


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = ['id', 'author_name', 'comment_text', 'created_at']

    def get_author_name(self, obj: TicketComment) -> str:
        if obj.author:
            return obj.author.username
        return "Hệ thống"


class SupportRequestDetailSerializer(serializers.ModelSerializer):
    comments = serializers.SerializerMethodField()

    class Meta:
        model = SupportRequest
        fields = [
            'id', 'title', 'description', 'category', 'priority',
            'status', 'created_at', 'updated_at', 'comments',
        ]

    def get_comments(self, obj: SupportRequest) -> list[dict]:
        # Chỉ trả về comment công khai (is_internal=False)
        public_comments = obj.comments.filter(is_internal=False)
        return TicketCommentSerializer(public_comments, many=True).data
