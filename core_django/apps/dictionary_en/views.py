from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.core.cache import cache
from celery.result import AsyncResult
import re

from .models import EnWord, EnExample
from .serializers import EnWordSerializer
from apps.ai_gateway import AIFallbackGateway
from .tasks import translate_en_pure_text_task
from apps.dictionary_zh.views import StandardResultsSetPagination

class EnWordSearchView(generics.ListAPIView):
    serializer_class = EnWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        db_shared_container = {}

        def db_lookup():
            queryset = self.get_queryset()
            exact_example = None
            query_word_len = len(query.split())

            if 1 <= query_word_len <= 30:
                cleaned_query = re.sub(r'[. , ! ?]+$', '', query)
                match = EnExample.objects.filter(english__iexact=cleaned_query).first()
                if match:
                    exact_example = {
                        'english': match.english,
                        'vietnamese': match.vietnamese
                    }

            has_data = queryset.exists() or (exact_example is not None)
            if has_data:
                db_shared_container['queryset'] = queryset
                db_shared_container['exact_example'] = exact_example
                return True
            return False

        # Tích hợp bảo vệ bằng Gateway dùng chung (Chế độ tiếng Anh 'en')
        gateway_response = AIFallbackGateway.handle_search_fallback(
            request=request,
            query=query,
            db_lookup_func=db_lookup,
            task_func=translate_en_pure_text_task,
            cache_key_prefix="ai_trans_en",
            mode='en'
        )

        if gateway_response:
            return gateway_response

        # DB Hit -> Lấy dữ liệu từ Closure tránh truy vấn trùng lặp
        queryset = db_shared_container['queryset']
        exact_example = db_shared_container['exact_example']

        page = self.paginate_queryset(queryset)
        if page is not None:
            response = self.get_paginated_response(self.get_serializer(page, many=True).data)
            response.data['exact_example_match'] = exact_example
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'exact_example_match': exact_example,
            'results': serializer.data
        })

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        if not query:
            return EnWord.objects.prefetch_related('examples').all()
        return EnWord.objects.prefetch_related('examples').filter(word__iexact=query)


class EnPureTextTranslationView(APIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        return AIFallbackGateway.handle_translation_fallback(
            request=request,
            task_func=translate_en_pure_text_task,
            cache_key_prefix="ai_trans_en",
            mode='en'
        )


class EnTranslationStatusView(APIView):
    def get(self, request, task_id):
        res = AsyncResult(task_id)
        if res.state == 'SUCCESS':
            result_data = res.result
            if result_data.get('status') == 'SUCCESS':
                return Response({
                    "status": "SUCCESS",
                    "translatedText": result_data.get('translatedText'),
                    "source": result_data.get('source')
                })
            return Response({
                "status": "FAILED", 
                "error": result_data.get('error', 'Lỗi không xác định')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif res.state == 'FAILURE':
            return Response({"status": "FAILED", "error": "Task execution failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"status": res.state})
