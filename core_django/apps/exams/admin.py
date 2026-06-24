from django.contrib import admin
from .models import Exam, Section, Question, Option

class SectionInline(admin.TabularInline):
    model = Section
    extra = 1

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

class OptionInline(admin.TabularInline):
    model = Option
    extra = 1

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('exam_id', 'exam_name', 'level', 'total_questions', 'total_time_minutes', 'total_score', 'status')
    list_filter = ('level', 'status', 'language')
    search_fields = ('exam_id', 'exam_name')
    inlines = [SectionInline]
    change_list_template = "admin/exams/exam_change_list.html"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('upload-exam/', self.admin_site.admin_view(self.upload_exam_view), name='exams_exam_upload_exam'),
        ]
        return custom_urls + urls

    def upload_exam_view(self, request):
        from django.shortcuts import render
        from django.contrib import messages
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        from .utils import import_full_exam_data

        if request.method == 'POST':
            exam_json = request.FILES.get('exam_json')
            audio_file = request.FILES.get('audio_file')
            image_mapping = request.FILES.get('image_mapping')
            images = request.FILES.getlist('images')

            if not exam_json:
                messages.error(request, "Vui lòng chọn file JSON đề thi.")
            else:
                try:
                    res = import_full_exam_data(
                        exam_json_file=exam_json,
                        audio_file=audio_file,
                        image_mapping_file=image_mapping,
                        images=images
                    )
                    messages.success(
                        request, 
                        f"Tải lên đề thi thành công! Exam ID: {res['exam_id']}, Images: {res['images_uploaded']}"
                    )
                    return HttpResponseRedirect(reverse('admin:exams_exam_changelist'))
                except ValueError as e:
                    messages.error(request, f"Lỗi dữ liệu: {e}")
                except Exception as e:
                    messages.error(request, f"Lỗi hệ thống: {e}")

        context = self.admin_site.each_context(request)
        context.update({
            'opts': self.model._meta,
            'title': 'Tải lên đề thi',
        })
        return render(request, 'admin/exams/upload_exam.html', context)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('exam', 'section_id', 'section_name')
    list_filter = ('section_name',)
    search_fields = ('section_id', 'exam__exam_name')
    inlines = [QuestionInline]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('section', 'question_id', 'question_type', 'points')
    list_filter = ('question_type',)
    search_fields = ('question_id', 'question_text')
    inlines = [OptionInline]

@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ('question', 'option_id', 'text')
    search_fields = ('option_id', 'text')
