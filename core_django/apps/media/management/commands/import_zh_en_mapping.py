"""
Management Command: import_zh_en_mapping

Import dữ liệu en_translation sạch từ file JSON HSK (1-9) 
vào bảng ZhEnMapping, phục vụ xây dựng Prompt cho AI Image Generation.

Chiến lược:
  - Đọc trường translation_en từ raw HSK JSON
  - Lấy từ khóa đầu tiên (trước dấu phẩy) làm en_translation sạch
  - Liên kết với ZhWord qua trường word + pinyin
  - Tìm kiếm EnWord tương ứng (optional, nullable)

Usage:
  python manage.py import_zh_en_mapping /path/to/word_data/raw/
  python manage.py import_zh_en_mapping /path/to/word_data/raw/ --dry-run
"""

import os
import json
import logging
from django.core.management.base import BaseCommand
from apps.media.models import ZhEnMapping
from apps.dictionary_zh.models import ZhWord
from apps.dictionary_en.models import EnWord

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import HSK translation_en data into ZhEnMapping table for AI prompt optimization'

    def add_arguments(self, parser):
        parser.add_argument(
            'data_dir',
            type=str,
            help='Path to the directory containing HSK JSON files (Hsk1.json, Hsk2.json, ...)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to database'
        )

    def handle(self, *args, **options):
        data_dir = options['data_dir']
        dry_run = options['dry_run']

        if not os.path.isdir(data_dir):
            self.stderr.write(self.style.ERROR(f"Directory not found: {data_dir}"))
            return

        # Discover HSK JSON files
        hsk_files = sorted([
            f for f in os.listdir(data_dir)
            if f.lower().startswith('hsk') and f.endswith('.json')
        ])

        if not hsk_files:
            self.stderr.write(self.style.ERROR(f"No HSK JSON files found in: {data_dir}"))
            return

        self.stdout.write(self.style.NOTICE(
            f"{'[DRY RUN] ' if dry_run else ''}Found {len(hsk_files)} HSK files: {', '.join(hsk_files)}"
        ))

        total_created = 0
        total_skipped = 0
        total_not_found = 0

        for hsk_file in hsk_files:
            file_path = os.path.join(data_dir, hsk_file)
            file_created, file_skipped, file_not_found = self._process_hsk_file(
                file_path, hsk_file, dry_run
            )
            total_created += file_created
            total_skipped += file_skipped
            total_not_found += file_not_found

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\n{'[DRY RUN] ' if dry_run else ''}=== Import Complete ===\n"
            f"  Created:   {total_created}\n"
            f"  Skipped:   {total_skipped} (already exists)\n"
            f"  Not Found: {total_not_found} (ZhWord not in DB)\n"
            f"  Total:     {total_created + total_skipped + total_not_found}"
        ))

    def _process_hsk_file(self, file_path, filename, dry_run):
        """Process a single HSK JSON file and create ZhEnMapping records."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                words_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.stderr.write(self.style.ERROR(f"Failed to read {filename}: {e}"))
            return 0, 0, 0

        created_count = 0
        skipped_count = 0
        not_found_count = 0

        self.stdout.write(f"\nProcessing {filename} ({len(words_data)} words)...")

        for entry in words_data:
            word_zh = entry.get('word', '').strip()
            pinyin = entry.get('pinyin', '').strip()
            translation_en_raw = entry.get('translation_en', '').strip()

            if not word_zh or not translation_en_raw:
                continue

            # Sanitize: lấy từ khóa đầu tiên trước dấu phẩy
            en_keyword = translation_en_raw.split(',')[0].strip()
            if not en_keyword:
                continue

            # Tìm ZhWord trong database
            zh_word = ZhWord.objects.filter(word=word_zh, pinyin=pinyin).first()
            if not zh_word:
                # Fallback: tìm chỉ theo word (trường hợp pinyin khác format nhỏ)
                zh_word = ZhWord.objects.filter(word=word_zh).first()

            if not zh_word:
                not_found_count += 1
                continue

            # Tìm EnWord tương ứng (optional)
            en_word = EnWord.objects.filter(word__iexact=en_keyword).first()

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {word_zh} ({pinyin}) → \"{en_keyword}\""
                    f"{' [+EnWord]' if en_word else ''}"
                )
                created_count += 1
                continue

            # Create or skip if already exists
            _, was_created = ZhEnMapping.objects.get_or_create(
                zh_word=zh_word,
                en_translation=en_keyword,
                defaults={'en_word': en_word}
            )

            if was_created:
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"  {filename}: +{created_count} created, "
            f"{skipped_count} skipped, "
            f"{not_found_count} not found"
        ))

        return created_count, skipped_count, not_found_count
