from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector
from django.db.models import Value
from apps.dictionary_zh.models import ZhExample
import jieba

class Command(BaseCommand):
    help = 'Updates the search_vector field for all existing ZhExample records using jieba.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Starting search_vector update...'))
        
        # Optimize by processing in chunks using iterator()
        examples = ZhExample.objects.all().iterator(chunk_size=2000)
        
        updated_count = 0
        for example in examples:
            if example.chinese:
                # Tokenize with jieba
                tokenized_chinese = " ".join(jieba.cut(example.chinese))
                
                # Perform a direct UPDATE query for each record to bypass save() overhead
                ZhExample.objects.filter(pk=example.pk).update(
                    search_vector=SearchVector(Value(tokenized_chinese), config='simple')
                )
                
                updated_count += 1
                if updated_count % 1000 == 0:
                    self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} examples...'))
                    
        self.stdout.write(self.style.SUCCESS(f'Finished! Total examples updated: {updated_count}'))
