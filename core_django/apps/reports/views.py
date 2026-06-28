from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.core import signing

from .serializers import (
    ContentReportCreateSerializer,
    FeatureReportCreateSerializer,
    FeatureReportListSerializer,
    SupportRequestCreateSerializer,
    SupportRequestListSerializer,
    SupportRequestDetailSerializer,
)
from .models import FeatureReport, SupportRequest
from .throttles import ReportAnonRateThrottle, ReportUserRateThrottle
from apps.media.tasks import trigger_image_regeneration_task

# Cấu hình Signed URL cho Guest ticket access
SUPPORT_TICKET_SALT = "support-ticket-access"
SUPPORT_TICKET_MAX_AGE = 7 * 24 * 3600  # 7 ngày (604800 giây)


class ContentReportView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ReportAnonRateThrottle, ReportUserRateThrottle]

    def post(self, request):
        serializer = ContentReportCreateSerializer(
            data=request.data,
            context={'request': request}
        )

        # Check validation errors
        if not serializer.is_valid():
            errors = serializer.errors
            # Nếu là lỗi trùng lặp (code='duplicate'), trả về HTTP 409 Conflict
            for field, err_list in errors.items():
                for err in err_list:
                    if getattr(err, 'code', None) == 'duplicate':
                        return Response(
                            {"detail": str(err)},
                            status=status.HTTP_409_CONFLICT
                        )
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        # Thiết lập reporter nếu user đã authenticated
        reporter = request.user if request.user.is_authenticated else None

        # Lưu vào Database
        report = serializer.save(reporter=reporter)

        # Kích hoạt nghiệp vụ tự động nếu report_type == 'image'
        if report.report_type == 'image':
            word_id = str(report.object_id)
            lang = 'zh' if report.content_type == 'zh_word' else 'en'
            guest_id = report.guest_id
            user_id = str(reporter.id) if reporter else (guest_id if str(guest_id).startswith('guest_') else f"guest_{guest_id}")

            # Đẩy Celery task xử lý tái sinh ảnh bất đồng bộ
            trigger_image_regeneration_task.apply_async(
                args=[word_id, lang, user_id],
                queue='queue_core'
            )

        return Response(
            {"detail": "Báo cáo lỗi đã được ghi nhận. Cảm ơn bạn đóng góp!", "id": report.id},
            status=status.HTTP_201_CREATED
        )


class FeatureReportView(APIView):
    """
    POST /api/v1/reports/features/ — Gửi đề xuất tính năng (auth + guest).
    GET  /api/v1/reports/features/ — Danh sách đề xuất của user đã đăng nhập.
    """
    throttle_classes = [ReportAnonRateThrottle, ReportUserRateThrottle]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]

    def post(self, request):
        serializer = FeatureReportCreateSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reporter = request.user if request.user.is_authenticated else None
        report = serializer.save(reporter=reporter)

        return Response(
            {"detail": "Cảm ơn bạn đã đóng góp ý kiến!", "id": str(report.id)},
            status=status.HTTP_201_CREATED
        )

    def get(self, request):
        reports = FeatureReport.objects.filter(reporter=request.user)
        serializer = FeatureReportListSerializer(reports, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SupportRequestView(APIView):
    """
    POST /api/v1/reports/support/ — Gửi yêu cầu hỗ trợ (auth + guest).
         Guest nhận signed_token trong response.
    GET  /api/v1/reports/support/ — Danh sách ticket của user đã đăng nhập.
    """
    throttle_classes = [ReportAnonRateThrottle, ReportUserRateThrottle]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        return [IsAuthenticated()]

    def post(self, request):
        serializer = SupportRequestCreateSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reporter = request.user if request.user.is_authenticated else None
        ticket = serializer.save(reporter=reporter)

        response_data: dict = {
            "detail": "Yêu cầu hỗ trợ đã được ghi nhận. Chúng tôi sẽ phản hồi sớm nhất!",
            "id": str(ticket.id),
        }

        # Nếu là Guest, tạo signed_token để truy cập ticket sau
        if not reporter:
            signed_token = signing.dumps(str(ticket.id), salt=SUPPORT_TICKET_SALT)
            response_data["signed_token"] = signed_token

        return Response(response_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        tickets = SupportRequest.objects.filter(reporter=request.user)
        serializer = SupportRequestListSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SupportRequestDetailView(APIView):
    """
    GET /api/v1/reports/support/<uuid:pk>/
    Chỉ cho phép authenticated user là chủ sở hữu ticket (IDOR protection).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            ticket = SupportRequest.objects.prefetch_related('comments').get(
                pk=pk, reporter=request.user
            )
        except SupportRequest.DoesNotExist:
            return Response(
                {"detail": "Không tìm thấy yêu cầu hỗ trợ."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = SupportRequestDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GuestTicketVerifyView(APIView):
    """
    GET /api/v1/reports/support/verify/?token=...
    Guest xác thực ticket bằng Signed URL token (max_age = 7 ngày).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response(
                {"detail": "Token không được cung cấp."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            ticket_id = signing.loads(
                token,
                salt=SUPPORT_TICKET_SALT,
                max_age=SUPPORT_TICKET_MAX_AGE
            )
        except signing.SignatureExpired:
            return Response(
                {"detail": "Token đã hết hạn. Vui lòng liên hệ hỗ trợ."},
                status=status.HTTP_403_FORBIDDEN
            )
        except signing.BadSignature:
            return Response(
                {"detail": "Token không hợp lệ."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            ticket = SupportRequest.objects.prefetch_related('comments').get(pk=ticket_id)
        except SupportRequest.DoesNotExist:
            return Response(
                {"detail": "Không tìm thấy yêu cầu hỗ trợ."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = SupportRequestDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GuestTicketBulkVerifyView(APIView):
    """
    POST /api/v1/reports/support/verify-bulk/
    Xác thực hàng loạt token trong một request duy nhất.
    Giải quyết lỗi N+1 requests khi Guest xem lịch sử ticket.

    Request body: { "tokens": ["token_1", "token_2", ...] }
    Response: { "tickets": [...], "invalid_count": 0 }
    """
    permission_classes = [AllowAny]
    throttle_classes = [ReportAnonRateThrottle]

    MAX_BULK_TOKENS = 20

    def post(self, request):
        tokens = request.data.get('tokens', [])

        if not isinstance(tokens, list) or not tokens:
            return Response(
                {"detail": "Danh sách token không hợp lệ."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(tokens) > self.MAX_BULK_TOKENS:
            return Response(
                {"detail": f"Tối đa {self.MAX_BULK_TOKENS} token mỗi lần xác thực."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Giải mã tất cả token hợp lệ, thu thập ticket IDs
        valid_ticket_ids: list[str] = []
        invalid_count = 0

        for token in tokens:
            try:
                ticket_id = signing.loads(
                    token,
                    salt=SUPPORT_TICKET_SALT,
                    max_age=SUPPORT_TICKET_MAX_AGE
                )
                valid_ticket_ids.append(ticket_id)
            except (signing.SignatureExpired, signing.BadSignature):
                invalid_count += 1

        # Batch query tất cả ticket hợp lệ trong một lần truy vấn DB duy nhất
        tickets = SupportRequest.objects.filter(
            pk__in=valid_ticket_ids
        ).order_by('-created_at')

        serializer = SupportRequestListSerializer(tickets, many=True)

        return Response(
            {"tickets": serializer.data, "invalid_count": invalid_count},
            status=status.HTTP_200_OK
        )
