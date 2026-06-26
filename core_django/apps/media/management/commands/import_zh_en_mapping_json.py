import os
import json
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.media.models import ZhEnMapping
from apps.dictionary_zh.models import ZhWord
from apps.dictionary_en.models import EnWord

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import ZH-EN mappings from zh_en_mapping.json'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, default='/app/data/en/zh_en_mapping.json', help='Path to the zh_en_mapping.json file')

    def handle(self, *args, **options):
        file_path = options['file']
        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.NOTICE(f"Loading {file_path}..."))
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.stdout.write(self.style.NOTICE(f"Found {len(data)} mapping records. Importing..."))
        
        # Load all existing ZhWord and EnWord IDs in database to check existence quickly
        self.stdout.write(self.style.NOTICE("Caching ZhWord and EnWord IDs..."))
        zh_ids = set(ZhWord.objects.values_list('id', flat=True))
        en_ids = set(EnWord.objects.values_list('id', flat=True))
        
        # Track existing mappings to avoid duplicates
        existing_mappings = set(ZhEnMapping.objects.values_list('zh_word_id', 'en_word_id'))
        
        mappings_to_create = []
        skipped_missing_zh = 0
        skipped_missing_en = 0
        skipped_duplicate = 0

        for item in data:
            zh_id = item.get("zh_word_id")
            en_id = item.get("en_word_id")
            caption = item.get("image_caption", "").strip()

            import uuid
            try:
                zh_uuid = uuid.UUID(zh_id)
                en_uuid = uuid.UUID(en_id)
            except:
                continue

            if zh_uuid not in zh_ids:
                skipped_missing_zh += 1
                continue
            if en_uuid not in en_ids:
                skipped_missing_en += 1
                continue
                
            if (zh_uuid, en_uuid) in existing_mappings:
                skipped_duplicate += 1
                continue

            mappings_to_create.append(ZhEnMapping(
                zh_word_id=zh_uuid,
                en_word_id=en_uuid,
                image_caption=caption
            ))
            existing_mappings.add((zh_uuid, en_uuid))

        self.stdout.write(self.style.NOTICE(f"Saving {len(mappings_to_create)} mappings to database..."))
        
        # Process in batches to avoid memory/db limits
        batch_size = 5000
        for i in range(0, len(mappings_to_create), batch_size):
            batch = mappings_to_create[i:i+batch_size]
            with transaction.atomic():
                ZhEnMapping.objects.bulk_create(batch)

        self.stdout.write(self.style.SUCCESS(
            f"Import complete!\n"
            f"  - Imported: {len(mappings_to_create)}\n"
            f"  - Skipped (Missing ZhWord): {skipped_missing_zh}\n"
            f"  - Skipped (Missing EnWord): {skipped_missing_en}\n"
            f"  - Skipped (Duplicate): {skipped_duplicate}"
        ))
