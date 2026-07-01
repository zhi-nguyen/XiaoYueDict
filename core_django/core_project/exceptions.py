import logging
from django.db import DatabaseError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("core_project.exceptions")

def custom_exception_handler(exc, context):
    """
    Custom exception handler for REST framework.
    Guarantees clean JSON output for infrastructure and database exceptions to prevent frontend crashes,
    while securely logging full tracebacks on the server.
    """
    # 1. Call DRF's default exception handler first to get the standard error response.
    response = exception_handler(exc, context)

    # 2. If response is None, it means DRF did not handle this exception (e.g. DatabaseError, ConnectionError, KeyError, etc.)
    if response is None:
        # Determine the request path and view name for logging context
        request = context.get('request')
        view = context.get('view')
        view_name = view.__class__.__name__ if view else "UnknownView"
        path = request.path if request else "UnknownPath"
        method = request.method if request else "UnknownMethod"

        # Log the full exception traceback securely on the server
        logger.error(
            f"❌ Unhandled Exception in view {view_name} on {method} {path}: {exc}",
            exc_info=True  # This captures and writes the full traceback to server logs
        )

        # Detect specific infrastructure/database exceptions
        exc_class_name = exc.__class__.__name__
        
        # Database connection or lock issues
        if isinstance(exc, DatabaseError) or "database" in exc_class_name.lower() or "operationalerror" in exc_class_name.lower():
            response = Response({
                "error": "DatabaseUnavailable",
                "message": "Dịch vụ tạm thời không khả dụng do sự cố kết nối cơ sở dữ liệu."
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
        # Redis/Cache connection issues
        elif "connectionerror" in exc_class_name.lower() or "redis" in exc_class_name.lower():
            response = Response({
                "error": "CacheServiceUnavailable",
                "message": "Dịch vụ tạm thời không khả dụng do sự cố hệ thống bộ nhớ đệm."
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
        # General unhandled code errors
        else:
            response = Response({
                "error": "InternalServerError",
                "message": "Đã xảy ra lỗi nội bộ trong hệ thống. Vui lòng liên hệ quản trị viên."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return response
