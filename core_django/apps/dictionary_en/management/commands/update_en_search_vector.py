from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector
from apps.dictionary_en.models import EnExample

class Command(BaseCommand):
    help = 'Updates the search_vector field for all existing EnExample records in bulk.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Starting bulk search_vector update for EnExample...'))
        
        # Perform a single bulk UPDATE query in database
        updated_count = EnExample.objects.all().update(
            search_vector=SearchVector('english', config='english')
        )
        
        self.stdout.write(self.style.SUCCESS(f'Finished! Total EnExample search_vectors updated in bulk: {updated_count}'))
