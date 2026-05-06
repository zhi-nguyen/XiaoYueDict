from rest_framework import serializers
from .models import AssessmentTask

class AssessmentTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentTask
        fields = ['id', 'status', 'score', 'created_at']
