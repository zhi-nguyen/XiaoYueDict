from django.contrib import admin
from .models import ZhWord, ZhExample

class ZhExampleInline(admin.TabularInline):
    model = ZhExample
    extra = 1

@admin.register(ZhWord)
class ZhWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'pinyin', 'han_viet', 'hsk_level', 'word_frequency', 'popularity_rank')
    list_filter = ('hsk_level',)
    search_fields = ('word', 'pinyin', 'han_viet')
    inlines = [ZhExampleInline]

@admin.register(ZhExample)
class ZhExampleAdmin(admin.ModelAdmin):
    list_display = ('word', 'chinese', 'vietnamese')
    search_fields = ('word__word', 'chinese', 'vietnamese')
