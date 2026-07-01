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
    GET/POST /api/v1/users/ws-token/
    Issues a short-lived JWT (2 minutes) specifically for WebSocket handshake.
    The token includes purpose='websocket' to prevent reuse as an access token.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return self._generate_token(request)

    def post(self, request):
        return self._generate_token(request)

    def _generate_token(self, request):
        now = datetime.now(timezone.utc)
        
        if request.user.is_authenticated:
            user_id = str(request.user.id)
            username = request.user.username
        else:
            # Guest logic
            if request.method == 'GET':
                guest_id = request.query_params.get('guest_id')
            else:
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
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        response = Response({"detail": "Đăng xuất thành công."}, status=200)
        
        access_cookie = settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
        refresh_cookie = settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token')
        
        response.delete_cookie(access_cookie, path='/')
        response.delete_cookie(refresh_cookie, path='/')
        return response


import os
import logging
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
firebase_key_path = os.path.join(settings.BASE_DIR, 'cnen-auth-key.json')
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(firebase_key_path)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")

class FirebaseLoginView(APIView):
    """
    API View to handle user authentication via Firebase ID Token.
    Verifies the ID Token, gets or creates the user in Django database, 
    and sets HttpOnly JWT cookies.
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        id_token = request.data.get('id_token')
        if not id_token:
            return Response({"detail": "Token ID không được cung cấp."}, status=400)

        try:
            # Verify the ID token
            decoded_token = firebase_auth.verify_id_token(id_token)
            uid = decoded_token.get('uid')
            email = decoded_token.get('email')
            name = decoded_token.get('name', '') or ''
        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return Response({"detail": "Token không hợp lệ hoặc đã hết hạn."}, status=401)

        User = get_user_model()
        user = None

        # 1. Try to find by firebase_uid
        try:
            user = User.objects.get(firebase_uid=uid)
        except User.DoesNotExist:
            pass

        # 2. Try to find by email and associate
        if not user and email:
            try:
                user = User.objects.get(email=email)
                user.firebase_uid = uid
                user.save()
            except User.DoesNotExist:
                pass

        # 3. Create a new user if they don't exist
        if not user:
            username = email.split('@')[0] if email else f"user_{uid[:8]}"
            # Ensure unique username
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1

            first_name = ''
            last_name = ''
            if name:
                parts = name.split(' ', 1)
                if len(parts) > 1:
                    first_name, last_name = parts[0], parts[1]
                else:
                    first_name = name

            from django.utils.crypto import get_random_string
            user = User.objects.create_user(
                username=username,
                email=email or '',
                password=get_random_string(32),
                first_name=first_name,
                last_name=last_name,
                firebase_uid=uid
            )

        # Update first_name and last_name if empty and name is available
        if name and not user.first_name and not user.last_name:
            parts = name.split(' ', 1)
            if len(parts) > 1:
                user.first_name, user.last_name = parts[0], parts[1]
            else:
                user.first_name = name
            user.save()

        # Sync profile picture from Google/Firebase asynchronously via Celery
        picture_url = decoded_token.get('picture')
        if picture_url and not user.avatar:
            from django.db import transaction
            from .tasks import sync_firebase_avatar_task

            transaction.on_commit(
                lambda: sync_firebase_avatar_task.apply_async(
                    args=[str(user.id), picture_url]
                )
            )


        # Generate SimpleJWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Build response and set cookies
        response = Response({
            "access": access_token,
            "refresh": refresh_token,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "bio": user.bio,
                "avatar": user.avatar.url if user.avatar else None,
            }
        }, status=200)

        # Retrieve cookie configs
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


