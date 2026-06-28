from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import UserSubscription, SubscriptionHistory, SubscriptionPlan
from .serializers import (
    UserSubscriptionSerializer, 
    SubscriptionHistorySerializer, 
    SubscriptionPlanSerializer,
    SubscriptionRegisterSerializer
)
from .services import MockPaymentService, SubscriptionManager
from core_project.ws_utils import get_redis_client

class SubscriptionPlanListView(generics.ListAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]
    queryset = SubscriptionPlan.objects.all().order_by('price')

class SubscriptionRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = SubscriptionRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_tier = serializer.validated_data['tier']
        user = request.user
        
        payment_service = MockPaymentService()
        manager = SubscriptionManager(payment_service)

        try:
            tiers = ['Free', 'Plus', 'Pro', 'Premium']
            sub = getattr(user, 'subscription', None)
            if not sub:
                sub = UserSubscription.objects.create(user=user, tier='Free')

            current_idx = tiers.index(sub.tier)
            target_idx = tiers.index(target_tier)

            if target_idx == current_idx:
                return Response(
                    {'error': f"Bạn đang sử dụng gói {target_tier} rồi."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif target_idx > current_idx:
                result = manager.upgrade_tier(user, target_tier)
            else:
                result = manager.request_downgrade(user, target_tier)
            
            sub_serializer = UserSubscriptionSerializer(user.subscription)
            return Response({
                'status': result['status'],
                'message': f"Yêu cầu xử lý thành công.",
                'subscription': sub_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'Có lỗi hệ thống xảy ra. Vui lòng liên hệ hỗ trợ.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CancelDowngradeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        payment_service = MockPaymentService()
        manager = SubscriptionManager(payment_service)

        try:
            result = manager.cancel_downgrade(user)
            sub_serializer = UserSubscriptionSerializer(user.subscription)
            return Response({
                'status': result['status'],
                'message': "Đã hủy yêu cầu hạ cấp thành công.",
                'subscription': sub_serializer.data
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'Có lỗi hệ thống xảy ra.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MySubscriptionView(generics.RetrieveAPIView):
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Trigger check_validity on fetch to auto-downgrade expired subs
        sub = getattr(self.request.user, 'subscription', None)
        if sub:
            sub.check_validity()
        return sub

from apps.dictionary_zh.views import StandardResultsSetPagination

class SubscriptionHistoryListView(generics.ListAPIView):
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return SubscriptionHistory.objects.filter(user=self.request.user).order_by('-changed_at')


from apps.assessments.utils import is_service_available

class SubscriptionUsageView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        r = get_redis_client()
        user = request.user
        
        if user and user.is_authenticated:
            user_id = f"user:{user.id}"
            tier_raw = getattr(user.subscription, 'tier', 'Free') if hasattr(user, 'subscription') else 'Free'
            tier = tier_raw.upper()
        else:
            guest_id = request.headers.get('X-Guest-ID') or request.GET.get('guest_id')
            identifier = guest_id if guest_id else request.META.get('REMOTE_ADDR', 'anonymous')
            user_id = f"guest:{identifier}"
            tier = 'GUEST'

        # 1. Lấy giới hạn cấu hình
        config_key = f"config:volume:{tier}"
        try:
            limits = r.hgetall(config_key)
        except Exception:
            limits = {}

        # Giải mã bytes của hash nếu Redis client trả về bytes
        limits_decoded = {}
        for k, v in limits.items():
            k_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
            v_str = v.decode('utf-8') if isinstance(v, bytes) else str(v)
            limits_decoded[k_str] = v_str

        limit_min = int(limits_decoded.get('min', 2 * 1024 * 1024))
        limit_hr = int(limits_decoded.get('hr', 20 * 1024 * 1024))
        limit_day = int(limits_decoded.get('day', 100 * 1024 * 1024))

        # 2. Đọc dung lượng đã tiêu thụ hiện tại từ Redis (an toàn fallback về 0)
        try:
            used_min_val = r.get(f"vol:{user_id}:min")
            used_hr_val = r.get(f"vol:{user_id}:hr")
            used_day_val = r.get(f"vol:{user_id}:day")
        except Exception:
            used_min_val = None
            used_hr_val = None
            used_day_val = None

        used_min = int(used_min_val or 0)
        used_hr = int(used_hr_val or 0)
        used_day = int(used_day_val or 0)

        return Response({
            'tier': tier,
            'limit_min': limit_min,
            'limit_hr': limit_hr,
            'limit_day': limit_day,
            'used_min': used_min,
            'used_hr': used_hr,
            'used_day': used_day,
            'service_available': is_service_available()
        }, status=status.HTTP_200_OK)

