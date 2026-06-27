from django.contrib import admin
from .models import EnWord, EnExample

class EnExampleInline(admin.TabularInline):
    model = EnExample
    extra = 1

@admin.register(EnWord)
class EnWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'ipa', 'cefr_level')
    list_filter = ('cefr_level',)
    search_fields = ('word', 'ipa')
    inlines = [EnExampleInline]

@admin.register(EnExample)
class EnExampleAdmin(admin.ModelAdmin):
    list_display = ('word', 'english', 'vietnamese')
    search_fields = ('word__word', 'english', 'vietnamese')
