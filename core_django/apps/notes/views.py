from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from rest_framework.permissions import IsAuthenticated

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

