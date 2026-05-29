from rest_framework import permissions

class IsPremiumUser(permissions.BasePermission):
    """
    Allows access only to users with Premium or Pro subscription.
    """
    message = "Tính năng này yêu cầu tài khoản Premium hoặc Pro."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Ensure subscription exists and is valid
        if hasattr(request.user, 'subscription'):
            sub = request.user.subscription
            if sub.check_validity() and sub.tier in ['Premium', 'Pro']:
                return True
        return False
