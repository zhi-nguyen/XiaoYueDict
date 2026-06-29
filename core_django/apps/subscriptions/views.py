import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import UserSubscription, SubscriptionHistory, SubscriptionPlan, PaymentOrder
from .serializers import (
    UserSubscriptionSerializer,
    SubscriptionHistorySerializer,
    SubscriptionPlanSerializer,
    SubscriptionRegisterSerializer,
    PaymentOrderSerializer,
)
from .services import SePayPaymentService, SubscriptionManager
from core_project.ws_utils import get_redis_client

logger = logging.getLogger(__name__)


class SubscriptionPlanListView(generics.ListAPIView):
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]
    queryset = SubscriptionPlan.objects.all().order_by('price')


class SubscriptionRegisterView(APIView):
    """
    Nâng cấp / Hạ cấp gói subscription.

    - Nâng cấp: Tạo PaymentOrder (PENDING) + trả QR data cho client.
    - Hạ cấp: Deferred downgrade (giữ quyền lợi đến hết kỳ) hoặc tức thì nếu là Premium.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = SubscriptionRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_tier = serializer.validated_data['tier']
        user = request.user

        manager = SubscriptionManager()

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
                # Nâng cấp → tạo đơn thanh toán, trả QR
                result = manager.initiate_upgrade(user, target_tier)
                return Response(result, status=status.HTTP_200_OK)
            else:
                # Hạ cấp
                result = manager.request_downgrade(user, target_tier)
                sub_serializer = UserSubscriptionSerializer(user.subscription)
                return Response({
                    'status': result['status'],
                    'message': 'Yêu cầu xử lý thành công.',
                    'subscription': sub_serializer.data
                }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Unexpected error in SubscriptionRegisterView")
            return Response(
                {'error': 'Có lỗi hệ thống xảy ra. Vui lòng liên hệ hỗ trợ.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CancelDowngradeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        manager = SubscriptionManager()

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
            logger.exception("Unexpected error in CancelDowngradeView")
            return Response(
                {'error': 'Có lỗi hệ thống xảy ra.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class SePayWebhookView(APIView):
    """
    Nhận IPN (Instant Payment Notification) từ SePay.
    
    Endpoint công khai (AllowAny), xác thực bằng HMAC-SHA256 signature.
    Không throttle — SePay cần gửi bất cứ lúc nào.
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # Không dùng JWT auth
    throttle_classes = []  # Không throttle webhook

    def post(self, request, *args, **kwargs):
        # 1. Xác thực HMAC signature
        signature = request.headers.get('Authorization', '')
        # SePay gửi signature dạng "Hmac <hex_signature>" hoặc trực tiếp
        if signature.startswith('Hmac '):
            signature = signature[5:]

        payment_service = SePayPaymentService()

        if not payment_service.verify_webhook_signature(request.body, signature):
            logger.warning("SePay webhook signature verification failed!")
            return Response(
                {'success': False, 'message': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 2. Parse payload
        try:
            payload = request.data
        except Exception:
            return Response(
                {'success': False, 'message': 'Invalid payload'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Xử lý webhook
        try:
            result = payment_service.handle_webhook(payload)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error processing SePay webhook: {e}")
            return Response(
                {'success': False, 'message': 'Internal error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentStatusView(APIView):
    """Client polling để kiểm tra trạng thái thanh toán."""
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id, *args, **kwargs):
        try:
            order = PaymentOrder.objects.get(id=order_id, user=request.user)
        except PaymentOrder.DoesNotExist:
            return Response(
                {'error': 'Đơn thanh toán không tồn tại.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Auto-expire nếu đã quá hạn
        if order.is_expired:
            order.status = 'EXPIRED'
            order.save(update_fields=['status'])

        data = PaymentOrderSerializer(order).data

        # Nếu đã thanh toán, kèm theo subscription info
        if order.status == 'PAID':
            sub = getattr(request.user, 'subscription', None)
            if sub:
                data['subscription'] = UserSubscriptionSerializer(sub).data

        return Response(data, status=status.HTTP_200_OK)


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
