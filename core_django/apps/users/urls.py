from django.urls import path
from .views import (
    UserRegistrationView, 
    UserProfileView, 
    ChangePasswordView, 
    WsTokenView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    CookieTokenLogoutView,
    FirebaseLoginView,
)

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='user_register'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('password/change/', ChangePasswordView.as_view(), name='change_password'),
    path('token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('token/logout/', CookieTokenLogoutView.as_view(), name='token_logout'),
    path('firebase-login/', FirebaseLoginView.as_view(), name='firebase_login'),
    path('ws-token/', WsTokenView.as_view(), name='ws_token'),
]


