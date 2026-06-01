from rest_framework import generics, permissions
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .serializers import UserRegistrationSerializer, UserDetailSerializer, ChangePasswordSerializer

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

from rest_framework import generics, permissions, parsers

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_object(self):
        return self.request.user

class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"detail": "Đổi mật khẩu thành công."}, status=200)
        return Response(serializer.errors, status=400)


from rest_framework.views import APIView
from django.conf import settings
from datetime import datetime, timedelta, timezone
import jwt
import uuid


class WsTokenView(APIView):
    """
    POST /api/v1/users/ws-token/
    Issues a short-lived JWT (2 minutes) specifically for WebSocket handshake.
    The token includes purpose='websocket' to prevent reuse as an access token.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        now = datetime.now(timezone.utc)
        
        if request.user.is_authenticated:
            user_id = str(request.user.id)
            username = request.user.username
        else:
            # Guest logic
            guest_id = request.data.get('guest_id')
            if not guest_id or not str(guest_id).startswith('guest_'):
                guest_id = f"guest_{uuid.uuid4().hex[:12]}"
            user_id = str(guest_id)
            username = "Guest"

        payload = {
            "user_id": user_id,
            "username": username,
            "purpose": "websocket",
            "iat": now,
            "exp": now + timedelta(minutes=2),
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        return Response({"ws_token": token, "user_id": user_id})

