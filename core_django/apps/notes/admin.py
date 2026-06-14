from django.contrib import admin
from .models import Notebook, Word, PDFExportTask


class WordInline(admin.TabularInline):
    model = Word
    extra = 1
    fields = ['vocabulary', 'pinyin', 'meaning', 'note']


@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ['name', 'word_count', 'created_at', 'updated_at']
    search_fields = ['name']
    inlines = [WordInline]


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ['vocabulary', 'pinyin', 'meaning', 'notebook', 'created_at']
    list_filter = ['notebook']
    search_fields = ['vocabulary', 'pinyin', 'meaning']


@admin.register(PDFExportTask)
class PDFExportTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'notebook', 'status', 'queue_name', 'created_at']
    list_filter = ['status', 'queue_name']
    search_fields = ['id', 'user__username', 'notebook__name']
