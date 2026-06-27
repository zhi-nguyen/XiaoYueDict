from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.middleware.csrf import CsrfViewMiddleware
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that reads the token from a secure HttpOnly cookie.
    Falls back to the standard Authorization: Bearer <token> header if not present in cookies.
    """
    def authenticate(self, request):
        header = self.get_header(request)
        raw_token = None

        if header is None:
            # Try to extract the access token from cookies
            access_cookie_name = settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
            raw_token = request.COOKIES.get(access_cookie_name)
            
            # If the token is found in the cookie, enforce CSRF protection (since cookies are automatically sent)
            if raw_token and settings.SIMPLE_JWT.get('AUTH_COOKIE_USE_CSRF', False):
                self.enforce_csrf(request)
        else:
            raw_token = self.get_raw_token(header)

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
        except Exception as e:
            logger.warning(f"JWT validation failed: {e}")
            return None

        return self.get_user(validated_token), validated_token

    def enforce_csrf(self, request):
        """
        Enforce CSRF validation for cookie-based authentication.
        Mimics Django's built-in CsrfViewMiddleware check.
        """
        csrf_middleware = CsrfViewMiddleware(lambda req: None)
        
        # Populate session/meta fields required by CsrfViewMiddleware
        csrf_middleware.process_request(request)
        
        # Returns None if CSRF validation passes, otherwise returns a HttpResponseForbidden with the error details
        reason = csrf_middleware.process_view(request, None, (), {})
        
        if reason:
            logger.warning(f"CSRF verification failed: {reason.content.decode('utf-8', errors='ignore')}")
            # Raise an AuthenticationFailed exception so DRF returns a 403 Forbidden
            raise AuthenticationFailed('CSRF verification failed.')
