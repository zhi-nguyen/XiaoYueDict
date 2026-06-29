from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import Q, Case, When, Value, IntegerField, F, Exists, OuterRef
from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import Length, StrIndex
from django.core.cache import cache

from .models import ZhWord, ZhExample
from .serializers import ZhWordSerializer, ZhCharacterBriefSerializer
from apps.ai_gateway import AIFallbackGateway
import re
import jieba
import unicodedata

def is_chinese_char(c: str) -> bool:
    """
    Kiểm tra ký tự truyền vào có thuộc nhóm chữ Hán (CJK Unified Ideograph) hay không,
    bao gồm cả các dải ký tự mở rộng (Extension A-H).
    """
    return 'CJK UNIFIED IDEOGRAPH' in unicodedata.name(c, '')


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ZhWordSearchView(generics.ListAPIView):
    serializer_class = ZhWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        from .tasks import translate_pure_text_task

        db_shared_container = {}

        # Check if fallback is disabled
        fallback_param = request.query_params.get('fallback', 'true').lower() == 'true'
        is_chinese = any(is_chinese_char(c) for c in query)
        q_lower = query.lower()

        if fallback_param:
            def db_lookup():
                exact_example = None
                cleaned_for_search = re.sub(r'[。，、！？. , ! ? : ： ; ； ( ) （ ） \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
                query_len = len(query)

                # 1. Check exact examples using language-specific fast checks
                if 2 <= query_len <= 100:
                    from .models import ZhExample
                    cleaned_query_end = re.sub(r'[。，、！？. , ! ?]+$', '', query)
                    
                    if is_chinese:
                        # For Chinese, exact sentence match only
                        regex_pattern = r'^' + re.escape(cleaned_query_end) + r'[。，、！？. , ! ?]*$'
                        match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
                        if not match and cleaned_for_search and len(cleaned_for_search) > 4:
                            match = ZhExample.objects.filter(chinese__icontains=cleaned_for_search).first()
                    else:
                        # For Latin/Vietnamese/English queries
                        match = ZhExample.objects.filter(vietnamese__icontains=cleaned_for_search).first()
                    
                    if match:
                        exact_example = {
                            'id': str(match.id),
                            'chinese': match.chinese,
                            'pinyin': match.pinyin,
                            'vietnamese': match.vietnamese
                        }

                # 2. Check if there are matches in ZhWord using very fast B-tree index queries
                if is_chinese:
                    has_exact_word = ZhWord.objects.filter(Q(word=cleaned_for_search) | Q(traditional=cleaned_for_search)).exists()
                    has_data = has_exact_word or (exact_example is not None)
                else:
                    # For English/Pinyin, check exact pinyin or translation_vi startswith (fast indexed scan)
                    q_clean_lower = cleaned_for_search.lower()
                    has_exact_pinyin = ZhWord.objects.filter(Q(pinyin=q_clean_lower) | Q(toneless_pinyin=q_clean_lower)).exists()
                    if has_exact_pinyin:
                        has_data = True
                    else:
                        # Fallback to general queryset check but only fetch ID to avoid overhead
                        queryset = self.filter_queryset(self.get_queryset())
                        has_data = queryset.only('id').exists() or (exact_example is not None)

                if has_data:
                    if 'queryset' not in db_shared_container:
                        db_shared_container['queryset'] = self.filter_queryset(self.get_queryset())
                    db_shared_container['exact_example'] = exact_example
                    return True
                return False

            # Ủy thác phòng thủ cho Gateway dùng chung (Chế độ tiếng Trung)
            gateway_response = AIFallbackGateway.handle_search_fallback(
                request=request,
                query=query,
                db_lookup_func=db_lookup,
                task_func=translate_pure_text_task,
                cache_key_prefix="ai_trans",
                mode='zh'
            )

            if gateway_response:
                return gateway_response
        else:
            queryset = self.filter_queryset(self.get_queryset())
            db_shared_container['queryset'] = queryset
            db_shared_container['exact_example'] = None

        # Check cache for DB search results
        hsk = request.query_params.get('hsk', '').strip()
        page = request.query_params.get('page', '1')
        import hashlib
        hashed_query = hashlib.md5(query.encode('utf-8')).hexdigest()
        cache_key = f"zh:search:{hashed_query}:{hsk}:{page}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        # Phục hồi dữ liệu từ Closure, triệt tiêu Double Query!
        queryset = db_shared_container['queryset']
        exact_example = db_shared_container['exact_example']

        page = self.paginate_queryset(queryset)
        if page is not None:
            res_data = self.get_paginated_response(self.get_serializer(page, many=True).data).data
            res_data['exact_example_match'] = exact_example
            import random
            ttl = 24 * 3600 + random.randint(0, 1800)  # 24h + jitter
            cache.set(cache_key, res_data, timeout=ttl)
            return Response(res_data)

        serializer = self.get_serializer(queryset, many=True)
        res_data = {
            'exact_example_match': exact_example,
            'results': serializer.data
        }
        import random
        ttl = 24 * 3600 + random.randint(0, 1800)
        cache.set(cache_key, res_data, timeout=ttl)
        return Response(res_data)


    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        hsk = self.request.query_params.get('hsk', '').strip()
        
        # Base Queryset with prefetch to solve N+1 Problem
        queryset = ZhWord.objects.prefetch_related('examples')
        
        if hsk:
            queryset = queryset.filter(hsk_level=hsk)
            
        # Clean query: strip Chinese and English punctuation
        cleaned_query = re.sub(r'[。，、！？. , ! ? : ： ; ； ( ) （ ） \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
            
        if not cleaned_query:
            # If no query but HSK is provided, just return paginated results ordered by popularity
            return queryset.annotate(
                adjusted_rank=Case(
                    When(popularity_rank=0, then=Value(999999)),
                    default='popularity_rank',
                    output_field=IntegerField(),
                )
            ).order_by('adjusted_rank')

        q_lower = cleaned_query.lower()
        is_chinese = any(is_chinese_char(c) for c in cleaned_query)

        # --- Pre-filtering optimization based on language ---
        if is_chinese:
            # 1. Chinese Query Flow
            filter_q = Q(word__exact=cleaned_query) | Q(traditional__exact=cleaned_query) | \
                       Q(word__startswith=cleaned_query) | Q(traditional__startswith=cleaned_query)
            
            # Tokenize query for FTS Search
            tokenized_query = " ".join(jieba.cut(cleaned_query))
            query_obj = SearchQuery(tokenized_query, config='simple')
            
            example_word_ids = list(
                ZhExample.objects.filter(
                    search_vector=query_obj
                ).values_list('word_id', flat=True).distinct()
            )
            if example_word_ids:
                filter_q |= Q(id__in=example_word_ids)

            # Generate substrings of query for fast word_idx match
            # substrings = []
            # for i in range(len(cleaned_query)):
            #     for j in range(i + 2, len(cleaned_query) + 1):
            #         sub = cleaned_query[i:j].strip()
            #         if sub and len(sub) >= 2:
            #             substrings.append(sub)
            # substrings = list(set(substrings))
            # if substrings:
            #     filter_q |= Q(word__in=substrings)
                
            queryset = queryset.filter(filter_q)
            has_example_match = Exists(
                ZhExample.objects.filter(word_id=OuterRef('pk'), search_vector=query_obj)
            )
            
            # Match levels for Chinese: 1, 3, 7, 8
            queryset = queryset.annotate(
                word_len=Length('word'),
                word_idx=StrIndex(Value(cleaned_query), F('word'))
            ).annotate(
                match_level=Case(
                    When(Q(word__exact=cleaned_query) | Q(traditional__exact=cleaned_query), then=Value(1)),
                    When(Q(word__startswith=cleaned_query) | Q(traditional__startswith=cleaned_query), then=Value(3)),
                    When(has_example_match, then=Value(7)),
                    When(word_idx__gt=0, then=Value(8)),
                    default=Value(999999),
                    output_field=IntegerField(),
                ),
                adjusted_rank=Case(
                    When(popularity_rank=0, then=Value(999999)),
                    default='popularity_rank',
                    output_field=IntegerField(),
                )
            )
        else:
            # 2. Latin (Vietnamese, English, Pinyin, Hán Việt) Query Flow
            filter_q = Q(toneless_pinyin__iexact=q_lower) | Q(pinyin__iexact=q_lower) | \
                       Q(toneless_pinyin__istartswith=q_lower) | Q(pinyin__istartswith=q_lower)
            
            if len(cleaned_query) >= 2:
                filter_q |= Q(translation_en__iexact=q_lower) | Q(han_viet__iexact=q_lower) | \
                           Q(translation_vi__icontains=q_lower) | Q(han_viet__icontains=q_lower) | \
                           Q(translation_en__icontains=q_lower)
                
                # Check vietnamese matching in ZhExample
                example_word_ids = list(
                    ZhExample.objects.filter(
                        vietnamese__icontains=cleaned_query
                    ).values_list('word_id', flat=True).distinct()
                )
                if example_word_ids:
                    filter_q |= Q(id__in=example_word_ids)

            queryset = queryset.filter(filter_q)
            
            has_example_match = Exists(
                ZhExample.objects.filter(word_id=OuterRef('pk'), vietnamese__icontains=cleaned_query)
            )
            
            # Match levels for Latin: 2, 4, 5, 6, 7, 8
            queryset = queryset.annotate(
                word_len=Length('word'),
                word_idx=StrIndex(Value(cleaned_query), F('word'))
            ).annotate(
                match_level=Case(
                    When(Q(toneless_pinyin__iexact=q_lower) | Q(pinyin__iexact=q_lower), then=Value(2)),
                    When(Q(toneless_pinyin__istartswith=q_lower) | Q(pinyin__istartswith=q_lower), then=Value(4)),
                    When(Q(translation_en__iexact=q_lower) | Q(han_viet__iexact=q_lower), then=Value(5)),
                    When(Q(translation_vi__icontains=q_lower) | Q(han_viet__icontains=q_lower) | Q(translation_en__icontains=q_lower), then=Value(6)),
                    When(has_example_match, then=Value(7)),
                    When(word_idx__gt=0, then=Value(8)),
                    default=Value(999999),
                    output_field=IntegerField(),
                ),
                adjusted_rank=Case(
                    When(popularity_rank=0, then=Value(999999)),
                    default='popularity_rank',
                    output_field=IntegerField(),
                )
            )

        # 3. Conditional sorting length exclusively for Match Level 8
        queryset = queryset.annotate(
            reverse_sort_len=Case(
                When(match_level=8, then=F('word_len')),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

        # 4. Filter match levels
        if len(cleaned_query) >= 2:
            queryset = queryset.filter(match_level__lte=8)
        else:
            queryset = queryset.filter(match_level__lte=7)
            
        # 5. Final Sort Order
        queryset = queryset.order_by('match_level', '-reverse_sort_len', 'adjusted_rank', 'word_frequency')
        
        return queryset

from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.response import Response
from rest_framework import status
import os
from .tasks import translate_pure_text_task
from celery.result import AsyncResult

class PureTextTranslationView(APIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        from .tasks import translate_pure_text_task
        return AIFallbackGateway.handle_translation_fallback(
            request=request,
            task_func=translate_pure_text_task,
            cache_key_prefix="ai_trans",
            mode='zh'
        )

class TranslationStatusView(APIView):
    throttle_classes = []

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
            else:
                return Response({
                    "status": "FAILED", 
                    "error": result_data.get('error', 'Lỗi không xác định')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        elif res.state == 'FAILURE':
            return Response({
                "status": "FAILED", 
                "error": "Task execution failed"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # Nếu vẫn đang chạy hoặc nằm trong hàng đợi
        return Response({"status": res.state})


class ZhWordBatchSearchView(generics.ListAPIView):
    serializer_class = ZhCharacterBriefSerializer
    pagination_class = None

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        query_type = self.request.query_params.get('type', 'char')
        
        if not query:
            return Response({'results': []})
            
        if query_type == 'char':
            # Tách chữ Hán mở rộng dùng is_chinese_char
            chars = list(set([c for c in query if is_chinese_char(c)]))
            if not chars:
                return Response({'results': []})
            
            # Tối ưu hóa bằng Redis cache.get_many()
            keys_map = {f"zh:char:{c}": c for c in chars}
            redis_keys = list(keys_map.keys())
            
            cached_results = cache.get_many(redis_keys)
            missing_chars = [keys_map[k] for k in redis_keys if k not in cached_results]
            
            new_serialized_data = {}
            if missing_chars:
                # Query nhanh không kèm ví dụ để giảm tải DB và payload size
                queryset = ZhWord.objects.filter(word__in=missing_chars)
                serializer = self.get_serializer(queryset, many=True)
                
                # Lưu các kết quả mới tìm được vào Redis
                to_cache = {f"zh:char:{item['word']}": item for item in serializer.data}
                if to_cache:
                    import random
                    ttl = 7 * 24 * 3600 + random.randint(0, 3600)  # 7 days + jitter
                    cache.set_many(to_cache, timeout=ttl)
                
                new_serialized_data = to_cache

            # Lắp ráp kết quả cuối cùng theo thứ tự danh sách chữ đầu vào
            final_results = []
            for c in chars:
                cache_key = f"zh:char:{c}"
                if cache_key in cached_results:
                    final_results.append(cached_results[cache_key])
                elif cache_key in new_serialized_data:
                    final_results.append(new_serialized_data[cache_key])
        else:
            return Response({'error': 'Invalid type parameter'}, status=400)
            
        return Response({'results': final_results})