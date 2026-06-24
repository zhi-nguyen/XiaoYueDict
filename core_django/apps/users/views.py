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
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
        return Response({"ws_token": token, "user_id": user_id})


from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

class CookieTokenObtainPairView(TokenObtainPairView):
    """
    Custom Token Obtain Pair View that sets access and refresh tokens as secure HTTP cookies
    in addition to returning them in the response body.
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')
            
            cookie_secure = settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', True)
            cookie_samesite = settings.SIMPLE_JWT.get('AUTH_COOKIE_SAME_SITE', 'Lax')
            cookie_httponly = settings.SIMPLE_JWT.get('AUTH_COOKIE_HTTPONLY', True)
            
            response.set_cookie(
                key=settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token'),
                value=access_token,
                max_age=settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME').total_seconds(),
                httponly=cookie_httponly,
                secure=cookie_secure,
                samesite=cookie_samesite,
                path='/',
            )
            response.set_cookie(
                key=settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token'),
                value=refresh_token,
                max_age=settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME').total_seconds(),
                httponly=cookie_httponly,
                secure=cookie_secure,
                samesite=cookie_samesite,
                path='/',
            )
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """
    Custom Token Refresh View that accepts refresh tokens from cookies or body,
    and sets/rotates cookies accordingly.
    """
    def post(self, request, *args, **kwargs):
        refresh_cookie_name = settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token')
        
        # If refresh token is not in the request body/JSON, check if it's in the cookies
        if 'refresh' not in request.data and refresh_cookie_name in request.COOKIES:
            # Safely modify request data
            if hasattr(request.data, '_mutable'):
                old_mutable = request.data._mutable
                request.data._mutable = True
                request.data['refresh'] = request.COOKIES[refresh_cookie_name]
                request.data._mutable = old_mutable
            else:
                try:
                    request.data['refresh'] = request.COOKIES[refresh_cookie_name]
                except TypeError:
                    request.data = request.data.copy()
                    request.data['refresh'] = request.COOKIES[refresh_cookie_name]

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')  # Returned if ROTATE_REFRESH_TOKENS is True
            
            cookie_secure = settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', True)
            cookie_samesite = settings.SIMPLE_JWT.get('AUTH_COOKIE_SAME_SITE', 'Lax')
            cookie_httponly = settings.SIMPLE_JWT.get('AUTH_COOKIE_HTTPONLY', True)
            
            response.set_cookie(
                key=settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token'),
                value=access_token,
                max_age=settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME').total_seconds(),
                httponly=cookie_httponly,
                secure=cookie_secure,
                samesite=cookie_samesite,
                path='/',
            )
            if refresh_token:
                response.set_cookie(
                    key=refresh_cookie_name,
                    value=refresh_token,
                    max_age=settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME').total_seconds(),
                    httponly=cookie_httponly,
                    secure=cookie_secure,
                    samesite=cookie_samesite,
                    path='/',
                )
        return response


class CookieTokenLogoutView(APIView):
    """
    API View to clear the access and refresh token cookies.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        response = Response({"detail": "Đăng xuất thành công."}, status=200)
        
        access_cookie = settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
        refresh_cookie = settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token')
        
        response.delete_cookie(access_cookie, path='/')
        response.delete_cookie(refresh_cookie, path='/')
        return response

