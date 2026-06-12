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
        Compute the queue position of this task relative to its specific physical queue.
        Position = number of PENDING/PROCESSING tasks in the same queue created BEFORE this one + 1.
        Returns 0 if the task is COMPLETED or FAILED.
        """
        if obj.status in ('COMPLETED', 'FAILED'):
            return 0

        ahead = AssessmentTask.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            queue_name=obj.queue_name,
            created_at__lt=obj.created_at,
        ).count()
        return ahead + 1

    def get_estimated_wait_seconds(self, obj):
        """
        Estimate wait time based on normalized EWT formula:
        EWT = ceil(position / concurrency) * processing_time_per_task
        """
        position = self.get_queue_position(obj)
        if position == 0:
            return 0

        import math
        concurrency = 2 if obj.queue_name == 'queue_paid' else 1
        processing_time_per_task = 7  # seconds
        
        return math.ceil(position / concurrency) * processing_time_per_task
