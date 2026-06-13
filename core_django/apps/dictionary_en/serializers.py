from rest_framework import serializers
from .models import EnWord, EnExample

class EnExampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnExample
        fields = ['english', 'vietnamese', 'audio_url']

class EnWordSerializer(serializers.ModelSerializer):
    examples = EnExampleSerializer(many=True, read_only=True)
    class Meta:
        model = EnWord
        fields = ['id', 'word', 'ipa', 'translation_vi', 'part_of_speech', 'cefr_level', 'audio_url', 'examples']
