import os
import json
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.dictionary_zh.models import ZhWord, ZhExample

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import HSK vocabulary data from JSON files'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='f:/BaiTap_DuAn/XiaoYue/none_sps/demo_hsk/word_data/final', help='Path to the directory containing JSON files')

    def handle(self, *args, **options):
        base_dir = options['path']
        levels = ["Hsk1", "Hsk2", "Hsk3", "Hsk4", "Hsk5", "Hsk6", "Hsk7-8-9"]

        def get_toneless_pinyin(pinyin_str):
            if not pinyin_str:
                return ""
            replacements = {
                'ā': 'a', 'á': 'a', 'ǎ': 'a', 'à': 'a',
                'ē': 'e', 'é': 'e', 'ě': 'e', 'è': 'e',
                'ī': 'i', 'í': 'i', 'ǐ': 'i', 'ì': 'i',
                'ō': 'o', 'ó': 'o', 'ǒ': 'o', 'ò': 'o',
                'ū': 'u', 'ú': 'u', 'ǔ': 'u', 'ù': 'u',
                'ǖ': 'v', 'ǘ': 'v', 'ǚ': 'v', 'ǜ': 'v', 'ü': 'v'
            }
            res = pinyin_str.lower()
            for k, v in replacements.items():
                res = res.replace(k, v)
            return res

        total_words_imported = 0
        total_examples_imported = 0

        # Load all existing words to memory to prevent duplicates efficiently
        existing_words = set(ZhWord.objects.values_list('word', flat=True))

        for level in levels:
            file_path = os.path.join(base_dir, f"{level}.json")
            if not os.path.exists(file_path):
                self.stdout.write(self.style.WARNING(f"File not found: {file_path}"))
                continue

            self.stdout.write(self.style.NOTICE(f"Processing {file_path}..."))
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            words_to_create = []
            examples_to_create = []

            for item in data:
                word_str = item.get("word", "")
                word_id = item.get("id")
                
                if not word_str or not word_id:
                    continue
                    
                if word_str in existing_words:
                    continue
                    
                pinyin_str = item.get("pinyin", "")
                toneless = get_toneless_pinyin(pinyin_str)

                word_obj = ZhWord(
                    id=word_id,
                    word=word_str,
                    traditional=item.get("traditional", ""),
                    pinyin=pinyin_str,
                    toneless_pinyin=toneless,
                    han_viet=item.get("han_viet", ""),
                    translation_vi=item.get("translation_vi", ""),
                    translation_en=item.get("translation_en", ""),
                    part_of_speech=item.get("part_of_speech", []),
                    hsk_level=item.get("hsk_level", ""),
                    radical=item.get("radical", []),
                    stroke_number=item.get("stroke_number", []),
                    components=item.get("components", []),
                    synonyms=item.get("synonyms", []),
                    antonyms=item.get("antonyms", []),
                    tags=item.get("tags", []),
                    word_frequency=item.get("word_frequency", 0.0) or 0.0,
                    popularity_rank=item.get("popularity_rank", 0) or 0,
                    audio_url=item.get("audio_url", "")
                )
                words_to_create.append(word_obj)
                existing_words.add(word_str)

                for ex in item.get("examples", []):
                    examples_to_create.append(ZhExample(
                        word=word_obj,
                        chinese=ex.get("chinese", ""),
                        pinyin=ex.get("pinyin", ""),
                        vietnamese=ex.get("vietnamese", ""),
                        audio_url=ex.get("audio_url", "")
                    ))

            with transaction.atomic():
                if words_to_create:
                    ZhWord.objects.bulk_create(words_to_create, batch_size=1000)
                    total_words_imported += len(words_to_create)

                if examples_to_create:
                    ZhExample.objects.bulk_create(examples_to_create, batch_size=2000)
                    total_examples_imported += len(examples_to_create)
                    
            self.stdout.write(self.style.SUCCESS(f"  -> Finished {level}.json (Imported {len(words_to_create)} words)"))

        self.stdout.write(self.style.SUCCESS(f"\nImport completed! Total words: {total_words_imported}. Total examples: {total_examples_imported}."))
