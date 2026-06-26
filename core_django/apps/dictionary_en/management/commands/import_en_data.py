import os
import json
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.dictionary_en.models import EnWord, EnExample

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import English vocabulary data from JSON files (A1.json to C2.json and 0.json)'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/app/data/en', help='Path to the directory containing JSON files')

    def handle(self, *args, **options):
        base_dir = options['path']
        levels = ["0", "A1", "A2", "B1", "B2", "C1", "C2"]

        total_words_imported = 0
        total_examples_imported = 0

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
                word_id = item.get("id")
                word_str = item.get("word")
                
                if not word_str or not word_id:
                    continue
                
                definitions = item.get("definitions", [])
                
                # Extract all unique parts of speech
                pos_list = []
                for d in definitions:
                    p = d.get("part_of_speech")
                    if p and p not in pos_list:
                        pos_list.append(p)
                
                # Extract all translations for translation_vi fallback
                trans_list = []
                for d in definitions:
                    t = d.get("translation_vi")
                    if t:
                        trans_list.append(t)
                trans_vi = "; ".join(trans_list)

                word_obj = EnWord(
                    id=word_id,
                    word=word_str[:100],
                    ipa=item.get("ipa", "")[:100],
                    translation_vi=trans_vi,
                    definitions=definitions,
                    part_of_speech=pos_list,
                    cefr_level=item.get("cefr_level", "")[:10],
                    core_inventory_1=item.get("core_inventory_1", "")[:255],
                    core_inventory_2=item.get("core_inventory_2", "")[:255],
                    threshold=item.get("threshold", "")[:255],
                    notes=item.get("notes", ""),
                    image_caption=item.get("image_caption", ""),
                    image_url=item.get("image_url", ""),
                    audio_url=""
                )
                words_to_create.append(word_obj)

                for d in definitions:
                    for ex in d.get("examples", []):
                        examples_to_create.append(EnExample(
                            word=word_obj,
                            english=ex.get("english", ""),
                            vietnamese=ex.get("vietnamese", ""),
                            audio_url=""
                        ))

            with transaction.atomic():
                if words_to_create:
                    EnWord.objects.bulk_create(words_to_create, batch_size=2000, ignore_conflicts=True)
                    total_words_imported += len(words_to_create)

                if examples_to_create:
                    EnExample.objects.bulk_create(examples_to_create, batch_size=5000, ignore_conflicts=True)
                    total_examples_imported += len(examples_to_create)
                    
            self.stdout.write(self.style.SUCCESS(f"  -> Finished {level}.json (Imported {len(words_to_create)} words)"))

        self.stdout.write(self.style.SUCCESS(f"\nImport completed! Total words: {total_words_imported}. Total examples: {total_examples_imported}."))
