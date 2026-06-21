from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from rest_framework import generics
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.http import Http404
from apps.subscriptions.permissions import IsPremiumUser
from rest_framework.pagination import PageNumberPagination
from apps.dictionary_zh.models import ZhWord
from apps.dictionary_zh.serializers import ZhWordSerializer
import datetime
from django.utils import timezone
from django.core.cache import cache
from apps.subscriptions.models import VolumeLimitConfig


from .models import Notebook, Word, PDFExportTask
from .serializers import (
    NotebookListSerializer,
    NotebookDetailSerializer,
    NotebookCreateSerializer,
    WordSerializer,
    WordCreateSerializer,
)


# ─── Notebook Views ─────────────────────────────────────────────

class NotebookListCreateView(APIView):
    """
    GET  /api/v1/notes/notebooks/          → Danh sách sổ tay
    POST /api/v1/notes/notebooks/          → Tạo sổ mới (chỉ cần name)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notebooks = Notebook.objects.filter(user=request.user).annotate(
            word_count_annotated=Count('words'),
        ).order_by('-updated_at')
        serializer = NotebookListSerializer(notebooks, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = NotebookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notebook = serializer.save(user=request.user)
        return Response(
            NotebookListSerializer(notebook).data,
            status=status.HTTP_201_CREATED,
        )


class NotebookDetailView(APIView):
    """
    GET    /api/v1/notes/notebooks/<id>/   → Chi tiết sổ + danh sách từ
    PATCH  /api/v1/notes/notebooks/<id>/   → Đổi tên / mô tả
    DELETE /api/v1/notes/notebooks/<id>/   → Xóa sổ
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, notebook_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        serializer = NotebookDetailSerializer(notebook)
        return Response(serializer.data)

    def patch(self, request, notebook_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        serializer = NotebookCreateSerializer(notebook, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(NotebookDetailSerializer(notebook).data)

    def delete(self, request, notebook_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        notebook.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Word Views ─────────────────────────────────────────────────

class WordListCreateView(APIView):
    """
    GET  /api/v1/notes/notebooks/<id>/words/    → Danh sách từ trong sổ
    POST /api/v1/notes/notebooks/<id>/words/    → Thêm từ vào sổ
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, notebook_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        words = notebook.words.all()

        # Tìm kiếm theo từ vựng hoặc nghĩa
        search = request.query_params.get('search', '').strip()
        if search:
            words = words.filter(
                Q(vocabulary__icontains=search)
                | Q(pinyin__icontains=search)
                | Q(meaning__icontains=search)
            )

        serializer = WordSerializer(words, many=True)
        return Response(serializer.data)

    def post(self, request, notebook_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        serializer = WordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        word = serializer.save(notebook=notebook)
        return Response(
            WordSerializer(word).data,
            status=status.HTTP_201_CREATED,
        )


class WordDetailView(APIView):
    """
    GET    /api/v1/notes/notebooks/<nb_id>/words/<word_id>/
    PATCH  /api/v1/notes/notebooks/<nb_id>/words/<word_id>/
    DELETE /api/v1/notes/notebooks/<nb_id>/words/<word_id>/
    """
    permission_classes = [IsAuthenticated]

    def _get_word(self, user, notebook_id, word_id):
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=user)
        return get_object_or_404(Word, pk=word_id, notebook=notebook)

    def get(self, request, notebook_id, word_id):
        word = self._get_word(request.user, notebook_id, word_id)
        return Response(WordSerializer(word).data)

    def patch(self, request, notebook_id, word_id):
        word = self._get_word(request.user, notebook_id, word_id)
        serializer = WordCreateSerializer(word, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WordSerializer(word).data)

    def delete(self, request, notebook_id, word_id):
        word = self._get_word(request.user, notebook_id, word_id)
        word.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Dictionary Lookup (Tra từ) ────────────────────────────────

class DictionaryLookupView(APIView):
    """
    GET /api/v1/notes/lookup/?q=你好
    Tra từ — tìm trong tất cả các sổ xem đã lưu chưa,
    và trả về kết quả gợi ý (nếu có).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {'error': 'Query parameter "q" is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tìm từ đã có trong các sổ của người dùng này
        existing_words = Word.objects.filter(notebook__user=request.user, vocabulary__iexact=query)
        existing_data = WordSerializer(existing_words, many=True).data

        return Response({
            'query': query,
            'existing_entries': existing_data,
        })

def get_seconds_until_midnight():
    """
    Tính toán chính xác số giây còn lại từ thời điểm hiện tại đến 00:00:00 ngày hôm sau (theo múi giờ địa phương).
    """
    now = timezone.localtime(timezone.now()) # Lấy thời gian hiện tại theo múi giờ địa phương cấu hình
    
    # Khởi tạo mốc thời gian 00:00:00 của ngày kế tiếp
    tomorrow = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time.min)
    
    # Áp dụng múi giờ hiện tại của hệ thống để đảm bảo tính toán khoảng cách giây chính xác
    tomorrow = timezone.make_aware(tomorrow, timezone.get_current_timezone())
    
    return int((tomorrow - now).total_seconds())


class NotebookExportPDFView(APIView):
    """
    POST /api/v1/notes/notebooks/<notebook_id>/export-pdf/
    Khởi tạo tác vụ bất đồng bộ kết xuất PDF và đưa vào hàng đợi tương ứng với gói dịch vụ.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, notebook_id):
        return self._handle_export(request, notebook_id)

    def get(self, request, notebook_id):
        # Hỗ trợ GET làm phương án dự phòng tương thích ngược
        return self._handle_export(request, notebook_id)

    def _handle_export(self, request, notebook_id):
        # 1. Xác thực và truy vấn dữ liệu từ vựng thuộc sổ tay
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        words = notebook.words.all().order_by('-created_at')

        # Hỗ trợ xuất tùy chọn một vài từ vựng được chọn
        word_ids_str = request.data.get('word_ids', request.query_params.get('word_ids', ''))
        if word_ids_str:
            try:
                word_ids = [int(x.strip()) for x in word_ids_str.split(',') if x.strip()]
                if word_ids:
                    words = words.filter(id__in=word_ids)
            except ValueError:
                pass

        # 2. Kiểm tra gói cước (Tier) và giới hạn
        sub = getattr(request.user, 'subscription', None)
        if sub:
            sub.check_validity()
            tier = sub.tier
        else:
            tier = 'Free'

        # Default fallback limits in case config doesn't exist in DB
        FALLBACK_LIMITS = {
            'Free': {'daily_limit': 2, 'max_words': 10},
            'Plus': {'daily_limit': 5, 'max_words': 40},
            'Premium': {'daily_limit': 10, 'max_words': 70},
            'Pro': {'daily_limit': 15, 'max_words': 100},
        }

        # Query limits dynamically from VolumeLimitConfig
        config = VolumeLimitConfig.objects.filter(tier=tier).first()
        if config:
            daily_limit = config.pdf_daily_limit
            max_words = config.pdf_word_limit
        else:
            fallback = FALLBACK_LIMITS.get(tier, FALLBACK_LIMITS['Free'])
            daily_limit = fallback['daily_limit']
            max_words = fallback['max_words']

        # Enforce maximum word count limit per PDF
        word_count = words.count()
        if word_count > max_words:
            return Response(
                {"detail": f"Gói {tier} chỉ được phép xuất tối đa {max_words} từ vựng mỗi file PDF (Hiện tại: {word_count} từ)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Enforce daily export limits (checked via Redis with midnight TTL reset)
        today_str = timezone.localtime(timezone.now()).date().isoformat()
        cache_key = f"pdf_export:count:{request.user.id}:{today_str}"

        # Atomic increment check
        try:
            current_count = cache.incr(cache_key)
        except ValueError:
            # Key does not exist, initialize it with remaining seconds until midnight
            cache.set(cache_key, 1, timeout=get_seconds_until_midnight())
            current_count = 1

        if current_count > daily_limit:
            # Over the limit: decrement and return 429
            cache.decr(cache_key)
            return Response(
                {"detail": f"Bạn đã vượt quá giới hạn xuất PDF trong ngày ({daily_limit} lần/ngày cho gói {tier})."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 3. Định dạng dữ liệu payload cho microservice
        words_data = []
        for w in words:
            words_data.append({
                "vocabulary": w.vocabulary,
                "pinyin": w.pinyin or "",
                "meaning": w.meaning or "",
                "note": w.note or ""
            })

        # Safe Options Sanitization (Data Sanitization & Parameter Overrides)
        get_param = lambda key, default: request.data.get(key, request.query_params.get(key, default))
        
        grid_color = get_param('grid_color', '#D32F2F')
        show_pinyin = str(get_param('show_pinyin', 'true')).lower() == 'true'
        show_meaning = str(get_param('show_meaning', 'true')).lower() == 'true'
        show_notes = str(get_param('show_notes', 'true')).lower() == 'true'

        safe_options = {
            "grid_color": grid_color,
            "show_pinyin": show_pinyin,
            "show_meaning": show_meaning,
            "show_notes": show_notes,
        }

        # Business Logic Guardrails (Khóa cứng cấu hình cho gói Free)
        if tier == 'Free':
            safe_options["show_cover"] = True
            safe_options["branding_name"] = "XiaoYue Dict"
        else:
            safe_options["show_cover"] = str(get_param('show_cover', 'true')).lower() == 'true'
            safe_options["branding_name"] = str(get_param('branding_name', 'XiaoYue Dict')).strip()

        # Handle other options safely
        try:
            extra_rows = int(get_param('extra_rows', '0'))
        except ValueError:
            extra_rows = 0

        try:
            empty_pages = int(get_param('empty_pages', '0'))
        except ValueError:
            empty_pages = 0

        empty_page_grid_size = get_param('empty_page_grid_size', 'auto')

        safe_options["extra_rows"] = extra_rows
        safe_options["empty_pages"] = empty_pages
        safe_options["empty_page_grid_size"] = empty_page_grid_size

        # Phân phối hàng đợi ưu tiên cho paid users
        if tier in ('Plus', 'Premium', 'Pro'):
            target_queue = 'queue_paid'
        else:
            target_queue = 'queue_free'

        # 4. Khởi tạo đối tượng PDFExportTask lưu trữ trong CSDL
        task = PDFExportTask.objects.create(
            user=request.user,
            notebook=notebook,
            status='PENDING',
            queue_name=target_queue
        )

        # 5. Kích hoạt Celery Task xử lý nền
        from .tasks import generate_pdf_task
        generate_pdf_task.apply_async(
            args=[
                str(task.id),
                notebook.id,
                request.user.id,
                words_data,
                safe_options,
                cache_key
            ],
            queue=target_queue
        )

        # 6. Tính toán vị trí hàng đợi động và thời gian chờ dự kiến
        pending_ahead = PDFExportTask.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            queue_name=target_queue,
            created_at__lt=task.created_at
        ).count()
        queue_position = pending_ahead + 1

        import math
        # Concurrency ước tính dựa trên cấu hình worker
        concurrency = 2 if target_queue == 'queue_paid' else 1
        processing_time_per_task = 10 # 10 giây/tệp
        estimated_wait_seconds = math.ceil(queue_position / concurrency) * processing_time_per_task

        return Response(
            {
                'task_id': str(task.id),
                'status': 'PENDING',
                'queue_position': queue_position,
                'estimated_wait_seconds': estimated_wait_seconds,
            },
            status=status.HTTP_202_ACCEPTED
        )


class PDFExportStatusView(APIView):
    """
    GET /api/v1/notes/notebooks/export-pdf/status/<task_id>/
    Trả về trạng thái hiện tại của tiến trình và vị trí hàng đợi.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = get_object_or_404(PDFExportTask, id=task_id)

        # IDOR Protection
        if task.user != request.user:
            return Response(
                {'detail': 'Bạn không có quyền xem thông tin tác vụ này.'},
                status=status.HTTP_403_FORBIDDEN
            )

        queue_position = 0
        estimated_wait_seconds = 0
        if task.status in ('PENDING', 'PROCESSING'):
            pending_ahead = PDFExportTask.objects.filter(
                status__in=['PENDING', 'PROCESSING'],
                queue_name=task.queue_name,
                created_at__lt=task.created_at
            ).count()
            queue_position = pending_ahead + 1

            import math
            concurrency = 2 if task.queue_name == 'queue_paid' else 1
            processing_time_per_task = 10
            estimated_wait_seconds = math.ceil(queue_position / concurrency) * processing_time_per_task

        return Response({
            'task_id': str(task.id),
            'status': task.status,
            'queue_position': queue_position,
            'estimated_wait_seconds': estimated_wait_seconds,
            'error_message': task.error_message,
            'created_at': task.created_at,
            'updated_at': task.updated_at,
        }, status=status.HTTP_200_OK)


class PDFExportDownloadView(APIView):
    """
    GET /api/v1/notes/notebooks/export-pdf/download/<task_id>/
    Tải xuống file PDF đã kết xuất nền hoàn tất.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = get_object_or_404(PDFExportTask, id=task_id)

        # IDOR Protection
        if task.user != request.user:
            return Response(
                {'detail': 'Bạn không có quyền tải file từ tác vụ này.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if task.status != 'COMPLETED' or not task.pdf_file:
            return Response(
                {'detail': 'Tệp PDF chưa hoàn thành hoặc tác vụ kết xuất thất bại.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        safe_name = task.notebook.name.lower().replace(' ', '-')
        response = FileResponse(
            task.pdf_file.open('rb'),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="so-tay-tap-viet-{safe_name}.pdf"'
        return response


class PDFExportLimitsView(APIView):
    """
    GET /api/v1/notes/notebooks/<notebook_id>/export-pdf/limits/
    Trả về hạn mức xuất PDF trong ngày và số từ tối đa dựa trên gói cước của người dùng.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, notebook_id):
        sub = getattr(request.user, 'subscription', None)
        if sub:
            sub.check_validity()
            tier = sub.tier
        else:
            tier = 'Free'

        FALLBACK_LIMITS = {
            'Free': {'daily_limit': 2, 'max_words': 10},
            'Plus': {'daily_limit': 5, 'max_words': 40},
            'Premium': {'daily_limit': 10, 'max_words': 70},
            'Pro': {'daily_limit': 15, 'max_words': 100},
        }

        # Query limits dynamically from VolumeLimitConfig
        config = VolumeLimitConfig.objects.filter(tier=tier).first()
        if config:
            daily_limit = config.pdf_daily_limit
            max_words = config.pdf_word_limit
        else:
            fallback = FALLBACK_LIMITS.get(tier, FALLBACK_LIMITS['Free'])
            daily_limit = fallback['daily_limit']
            max_words = fallback['max_words']

        # Get current usage from Redis
        today_str = timezone.localtime(timezone.now()).date().isoformat()
        cache_key = f"pdf_export:count:{request.user.id}:{today_str}"
        current_count = cache.get(cache_key) or 0

        remaining = max(0, daily_limit - current_count)

        return Response({
            'tier': tier,
            'daily_limit': daily_limit,
            'current_count': current_count,
            'remaining_count': remaining,
            'max_words': max_words,
        }, status=status.HTTP_200_OK)


@method_decorator(cache_page(60 * 60 * 24), name='dispatch')
class SystemNotebookListView(APIView):
    """
    GET /api/v1/notes/system-notebooks/
    Trả về danh mục các sổ tay hệ thống (HSK, Từ loại, Tags) kèm trạng thái Premium.
    Sử dụng bộ nhớ đệm cache_page với TTL 24h để tối ưu hiệu năng.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Count
        from apps.dictionary_zh.models import ZhWord
        
        # 1. Fetch HSK counts
        hsk_counts = dict(
            ZhWord.objects.values('hsk_level')
            .annotate(count=Count('id'))
            .values_list('hsk_level', 'count')
        )

        hsk_books = [
            {"id": "hsk_1", "name": "Từ vựng HSK 1", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 1", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("1", 0)},
            {"id": "hsk_2", "name": "Từ vựng HSK 2", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 2", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("2", 0)},
            {"id": "hsk_3", "name": "Từ vựng HSK 3", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 3", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("3", 0)},
            {"id": "hsk_4", "name": "Từ vựng HSK 4", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 4", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("4", 0)},
            {"id": "hsk_5", "name": "Từ vựng HSK 5", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 5", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("5", 0)},
            {"id": "hsk_6", "name": "Từ vựng HSK 6", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 6", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("6", 0)},
            {"id": "hsk_7-9", "name": "Từ vựng HSK 7-9", "description": "Sổ tay từ vựng luyện thi HSK cấp độ 7 - 9", "type": "hsk", "is_premium": False, "word_count": hsk_counts.get("7-9", 0)},
        ]
        
        pos_books = [
            {"id": "pos_noun", "name": "Danh từ (Noun)", "description": "Từ vựng phân loại theo Danh từ", "type": "pos", "is_premium": True},
            {"id": "pos_verb", "name": "Động từ (Verb)", "description": "Từ vựng phân loại theo Động từ", "type": "pos", "is_premium": True},
            {"id": "pos_adjective", "name": "Tính từ (Adjective)", "description": "Từ vựng phân loại theo Tính từ", "type": "pos", "is_premium": True},
            {"id": "pos_adverb", "name": "Phó từ (Adverb)", "description": "Từ vựng phân loại theo Phó từ", "type": "pos", "is_premium": True},
            {"id": "pos_idiom", "name": "Thành ngữ (Idiom)", "description": "Từ vựng phân loại theo Thành ngữ", "type": "pos", "is_premium": True},
            {"id": "pos_classifier", "name": "Lượng từ (Classifier)", "description": "Từ vựng phân loại theo Lượng từ", "type": "pos", "is_premium": True},
            {"id": "pos_conjunction", "name": "Liên từ (Conjunction)", "description": "Từ vựng phân loại theo Liên từ", "type": "pos", "is_premium": True},
            {"id": "pos_preposition", "name": "Giới từ (Preposition)", "description": "Từ vựng phân loại theo Giới từ", "type": "pos", "is_premium": True},
            {"id": "pos_pronoun", "name": "Đại từ (Pronoun)", "description": "Từ vựng phân loại theo Đại từ", "type": "pos", "is_premium": True},
        ]
        
        # 2. Count POS books
        for book in pos_books:
            pos_type = book["id"].replace("pos_", "")
            book["word_count"] = ZhWord.objects.filter(part_of_speech__contains=pos_type).count()
        
        tag_books = [
            {"id": "tag_人", "name": "Con người", "description": "Từ vựng chủ đề Con người", "type": "tag", "is_premium": True},
            {"id": "tag_实体", "name": "Thực thể", "description": "Từ vựng chủ đề Thực thể", "type": "tag", "is_premium": True},
            {"id": "tag_动物", "name": "Động vật", "description": "Từ vựng chủ đề Động vật", "type": "tag", "is_premium": True},
            {"id": "tag_商业", "name": "Thương mại", "description": "Từ vựng chủ đề Thương mại", "type": "tag", "is_premium": True},
            {"id": "tag_职位", "name": "Nghề nghiệp", "description": "Từ vựng chủ đề Nghề nghiệp", "type": "tag", "is_premium": True},
            {"id": "tag_事件", "name": "Sự kiện", "description": "Từ vựng chủ đề Sự kiện", "type": "tag", "is_premium": True},
            {"id": "tag_政", "name": "Chính trị", "description": "Từ vựng chủ đề Chính trị", "type": "tag", "is_premium": True},
            {"id": "tag_生理学", "name": "Sinh lý học", "description": "Từ vựng chủ đề Sinh lý học", "type": "tag", "is_premium": True},
            {"id": "tag_群体", "name": "Nhóm người", "description": "Từ vựng chủ đề Nhóm người", "type": "tag", "is_premium": True},
            {"id": "tag_家庭", "name": "Gia đình", "description": "Từ vựng chủ đề Gia đình", "type": "tag", "is_premium": True},
            {"id": "tag_物质", "name": "Vật chất", "description": "Từ vựng chủ đề Vật chất", "type": "tag", "is_premium": True},
            {"id": "tag_医", "name": "Y tế", "description": "Từ vựng chủ đề Y tế", "type": "tag", "is_premium": True},
            {"id": "tag_教育", "name": "Giáo dục", "description": "Từ vựng chủ đề Giáo dục", "type": "tag", "is_premium": True},
            {"id": "tag_金融", "name": "Tài chính", "description": "Từ vựng chủ đề Tài chính", "type": "tag", "is_premium": True},
            {"id": "tag_体育", "name": "Thể thao", "description": "Từ vựng chủ đề Thể thao", "type": "tag", "is_premium": True},
        ]
        
        # 3. Count Tag books
        for book in tag_books:
            tag_name = book["id"].replace("tag_", "")
            book["word_count"] = ZhWord.objects.filter(tags__contains=tag_name).count()
        
        return Response({
            "hsk": hsk_books,
            "pos": pos_books,
            "tag": tag_books
        })


class SystemNotebookPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class SystemNotebookWordsView(generics.ListAPIView):
    """
    GET /api/v1/notes/system-notebooks/<key>/words/
    Trả về danh sách từ vựng ảo (Virtual Query Routing) của sổ tay hệ thống.
    - HSK: tất cả mọi người có thể xem.
    - POS & Tag: chỉ Premium/Pro user được xem.
    """
    serializer_class = ZhWordSerializer
    pagination_class = SystemNotebookPagination

    def get_permissions(self):
        key = self.kwargs.get('key', '')
        if key.startswith('hsk_'):
            return [AllowAny()]
        return [IsPremiumUser()]

    def get_queryset(self):
        key = self.kwargs.get('key', '')
        queryset = ZhWord.objects.prefetch_related('examples').all()
        
        if key.startswith('hsk_'):
            hsk_level = key.replace('hsk_', '')
            return queryset.filter(hsk_level=hsk_level).order_by('popularity_rank', 'id')
            
        elif key.startswith('pos_'):
            pos_type = key.replace('pos_', '')
            return queryset.filter(part_of_speech__contains=pos_type).order_by('popularity_rank', 'id')
            
        elif key.startswith('tag_'):
            tag_name = key.replace('tag_', '')
            return queryset.filter(tags__contains=tag_name).order_by('popularity_rank', 'id')
            
        raise Http404("Danh mục sổ tay hệ thống không tồn tại.")


