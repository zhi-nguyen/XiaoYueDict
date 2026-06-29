from rest_framework import serializers
from .models import ZhWord, ZhExample

class ZhExampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZhExample
        fields = ['id', 'chinese', 'pinyin', 'vietnamese', 'audio_url']

class ZhWordSerializer(serializers.ModelSerializer):
    examples = ZhExampleSerializer(many=True, read_only=True)
    
    class Meta:
        model = ZhWord
        fields = [
            'id', 'word', 'traditional', 'pinyin', 'toneless_pinyin', 'han_viet',
            'translation_vi', 'translation_en', 'part_of_speech', 'hsk_level',
            'radical', 'stroke_number', 'components', 'synonyms', 'antonyms',
            'tags', 'word_frequency', 'popularity_rank', 'audio_url', 'image_url', 'examples'
        ]

class ZhCharacterBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZhWord
        fields = [
            'id', 'word', 'traditional', 'pinyin', 'han_viet',
            'translation_vi', 'radical', 'stroke_number',
            'components', 'popularity_rank'
        ]
