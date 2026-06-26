from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .serializers import ContentReportCreateSerializer
from .throttles import ReportAnonRateThrottle, ReportUserRateThrottle
from apps.media.tasks import trigger_image_regeneration_task

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
