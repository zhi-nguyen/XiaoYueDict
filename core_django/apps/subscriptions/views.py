from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import UserSubscription, SubscriptionHistory
from .serializers import UserSubscriptionSerializer, SubscriptionHistorySerializer
from core_project.ws_utils import get_redis_client

class MySubscriptionView(generics.RetrieveAPIView):
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Trigger check_validity on fetch to auto-downgrade expired subs
        sub = getattr(self.request.user, 'subscription', None)
        if sub:
            sub.check_validity()
        return sub

class SubscriptionHistoryListView(generics.ListAPIView):
    serializer_class = SubscriptionHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SubscriptionHistory.objects.filter(user=self.request.user).order_by('-changed_at')


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
            tier = 'FREE'

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
            'used_day': used_day
        }, status=status.HTTP_200_OK)

