from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
import requests


from .models import Notebook, Word
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


class NotebookExportPDFView(APIView):
    """
    GET /api/v1/notes/notebooks/<notebook_id>/export-pdf/
    Gọi đến microservice pdf-service ở dạng Stream để kết xuất vở tập viết tiếng Trung (Tianzige)
    với tùy chọn ngắt dòng tự động và căn lề bính âm đồng bộ.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, notebook_id):
        # 1. Xác thực và truy vấn dữ liệu từ vựng thuộc sổ tay
        notebook = get_object_or_404(Notebook, pk=notebook_id, user=request.user)
        words = notebook.words.all().order_by('-created_at')

        # Hỗ trợ xuất tùy chọn một vài từ vựng được chọn
        word_ids_str = request.query_params.get('word_ids', '')
        if word_ids_str:
            try:
                word_ids = [int(x.strip()) for x in word_ids_str.split(',') if x.strip()]
                if word_ids:
                    words = words.filter(id__in=word_ids)
            except ValueError:
                pass

        # 2. Định dạng dữ liệu payload cho microservice
        words_data = []
        for w in words:
            words_data.append({
                "vocabulary": w.vocabulary,
                "pinyin": w.pinyin or "",
                "meaning": w.meaning or "",
                "note": w.note or ""
            })

        # Lấy các options từ query params
        grid_color = request.query_params.get('grid_color', '#D32F2F')
        show_pinyin = request.query_params.get('show_pinyin', 'true').lower() == 'true'
        show_meaning = request.query_params.get('show_meaning', 'true').lower() == 'true'
        show_notes = request.query_params.get('show_notes', 'true').lower() == 'true'
        show_cover = request.query_params.get('show_cover', 'true').lower() == 'true'

        try:
            extra_rows = int(request.query_params.get('extra_rows', '0'))
        except ValueError:
            extra_rows = 0

        try:
            empty_pages = int(request.query_params.get('empty_pages', '0'))
        except ValueError:
            empty_pages = 0

        empty_page_grid_size = request.query_params.get('empty_page_grid_size', 'auto')

        payload = {
            "title": notebook.name,
            "words": words_data,
            "options": {
                "grid_color": grid_color,
                "show_pinyin": show_pinyin,
                "show_meaning": show_meaning,
                "show_notes": show_notes,
                "show_cover": show_cover,
                "extra_rows": extra_rows,
                "empty_pages": empty_pages,
                "empty_page_grid_size": empty_page_grid_size
            }
        }

        # 3. Kết nối microservice với chế độ stream=True (Zero-Copy Pass-Through)
        fastapi_url = "http://pdf-service:8082/generate"
        try:
            upstream_response = requests.post(fastapi_url, json=payload, stream=True, timeout=60)
            upstream_response.raise_for_status()
        except requests.RequestException as e:
            return Response(
                {"detail": f"Dịch vụ biên tập PDF đang bận hoặc gặp sự cố: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 4. Định tuyến dòng chảy dữ liệu trực tiếp sang client socket
        response = FileResponse(
            upstream_response.raw,
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="so-tay-tap-viet.pdf"'
        return response


