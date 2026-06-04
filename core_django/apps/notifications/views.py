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
