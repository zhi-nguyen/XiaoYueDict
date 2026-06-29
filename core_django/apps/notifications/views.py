from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Notification
from .serializers import NotificationSerializer


class UnreadNotificationsView(APIView):
    """
    GET /api/v1/notifications/unread/
    Returns all unread notifications for the authenticated user.
    Called by the client on WebSocket reconnect to recover missed messages.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(
            user=request.user,
            is_read=False,
        )[:50]  # Limit to 50 most recent unread

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarkNotificationsReadView(APIView):
    """
    POST /api/v1/notifications/mark-read/
    Body: {"ids": [1, 2, 3]} or {"all": true}
    Marks notifications as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mark_all = request.data.get('all', False)
        ids = request.data.get('ids', [])

        if mark_all:
            count = Notification.objects.filter(
                user=request.user,
                is_read=False,
            ).update(is_read=True)
        elif ids:
            count = Notification.objects.filter(
                user=request.user,
                id__in=ids,
                is_read=False,
            ).update(is_read=True)
        else:
            return Response(
                {'error': 'Provide "ids" list or "all": true'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'marked_read': count}, status=status.HTTP_200_OK)


class UnreadCountView(APIView):
    """
    GET /api/v1/notifications/count/
    Returns the count of unread notifications (lightweight endpoint for badges).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return Response({'unread_count': count}, status=status.HTTP_200_OK)


from rest_framework.pagination import PageNumberPagination


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationListView(APIView):
    """
    GET /api/v1/notifications/
    Returns a paginated list of all notifications for the user (both read and unread).
    Query params:
        - page: Page number (default: 1)
        - is_read: Filter by read status (true/false, optional)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        is_read_filter = request.query_params.get('is_read')
        if is_read_filter is not None:
            is_read_bool = is_read_filter.lower() in ('true', '1', 't')
            notifications = notifications.filter(is_read=is_read_bool)

        paginator = NotificationPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)
        if page is not None:
            serializer = NotificationSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)

