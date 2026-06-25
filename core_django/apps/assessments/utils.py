import time
from django.conf import settings
from core_project.ws_utils import get_redis_client

_maintenance_status = None
_last_maintenance_check = 0

def is_service_available() -> bool:
    """
    Check if the AI assessment service is available.
    Uses layered caching: stores the state in local memory for 15 seconds
    to prevent excessive Redis I/O queries under high traffic.
    """
    global _maintenance_status, _last_maintenance_check
    now = time.time()
    if now - _last_maintenance_check < 15 and _maintenance_status is not None:
        return _maintenance_status
        
    r = get_redis_client()
    try:
        val = r.get("config:service_available")
        if val is not None:
            status = val.decode('utf-8').lower() == 'true'
        else:
            status = getattr(settings, 'AI_SERVICE_AVAILABLE', True)
    except Exception:
        status = getattr(settings, 'AI_SERVICE_AVAILABLE', True)
        
    _maintenance_status = status
    _last_maintenance_check = now
    return _maintenance_status
