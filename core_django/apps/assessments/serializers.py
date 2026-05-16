from rest_framework import serializers
from .models import AssessmentTask


class AssessmentSubmitSerializer(serializers.Serializer):
    """Validates incoming audio submission requests."""
    audio = serializers.FileField(required=True)
    target_text = serializers.CharField(required=False, default='', allow_blank=True)
    language = serializers.ChoiceField(choices=['en', 'zh'], default='en')


class AssessmentTaskSerializer(serializers.ModelSerializer):
    """Serializes task status responses including queue position."""
    queue_position = serializers.SerializerMethodField()
    estimated_wait_seconds = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentTask
        fields = [
            'id', 'status', 'language', 'score',
            'result_data', 'error_message',
            'queue_position', 'estimated_wait_seconds',
            'created_at',
        ]

    def get_queue_position(self, obj):
        """
        Compute the queue position of this task.
        Position = number of PENDING/PROCESSING tasks created BEFORE this one + 1.
        Returns 0 if the task is COMPLETED or FAILED.
        """
        if obj.status in ('COMPLETED', 'FAILED'):
            return 0

        ahead = AssessmentTask.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            created_at__lt=obj.created_at,
        ).count()
        return ahead + 1

    def get_estimated_wait_seconds(self, obj):
        """
        Estimate wait time based on queue position.
        Average processing time per task: ~7 seconds (5-10s budget).
        """
        position = self.get_queue_position(obj)
        if position == 0:
            return 0
        return position * 7
