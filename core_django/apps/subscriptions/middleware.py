import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from core_project.ws_utils import get_redis_client

logger = logging.getLogger(__name__)

LUA_RATE_LIMITER = """
-- keys: KEYS[1] (min), KEYS[2] (hr), KEYS[3] (day)
-- args: ARGV[1] (incoming_bytes), ARGV[2] (limit_min), ARGV[3] (limit_hr), ARGV[4] (limit_day)

local incoming = tonumber(ARGV[1])
local limit_min = tonumber(ARGV[2])
local limit_hr = tonumber(ARGV[3])
local limit_day = tonumber(ARGV[4])

-- Đọc dung lượng đã tiêu thụ hiện tại từ Redis
local cur_min = tonumber(redis.call('GET', KEYS[1]) or 0)
local cur_hr = tonumber(redis.call('GET', KEYS[2]) or 0)
local cur_day = tonumber(redis.call('GET', KEYS[3]) or 0)

-- Kiểm tra giới hạn theo từng khung thời gian
if (cur_min + incoming > limit_min) then 
    return {0, redis.call('TTL', KEYS[1]), 'minute'}
end

if (cur_hr + incoming > limit_hr) then 
    local ttl = redis.call('TTL', KEYS[2])
    -- Nếu key chưa được thiết lập TTL (trả về -1), mặc định thời gian hồi là 1 giờ (3600s)
    return {0, ttl > 0 and ttl or 3600, 'hour'}
end

if (cur_day + incoming > limit_day) then 
    local ttl = redis.call('TTL', KEYS[3])
    -- Nếu key chưa được thiết lập TTL (trả về -1), mặc định thời gian hồi là 1 ngày (86400s)
    return {0, ttl > 0 and ttl or 86400, 'day'}
end

-- Nếu tất cả các điều kiện hợp lệ, tiến hành cộng dồn dung lượng tệp
local res_min = redis.call('INCRBY', KEYS[1], incoming)
local res_hr = redis.call('INCRBY', KEYS[2], incoming)
local res_day = redis.call('INCRBY', KEYS[3], incoming)

-- Thiết lập thời gian hết hạn (TTL) cho các khóa mới khởi tạo
if res_min == incoming then redis.call('EXPIRE', KEYS[1], 60) end
if res_hr == incoming then redis.call('EXPIRE', KEYS[2], 3600) end
if res_day == incoming then redis.call('EXPIRE', KEYS[3], 86400) end

return {1, 0, ''} -- Trả về 1 xác nhận yêu cầu thành công, cho phép đi tiếp
"""

class VolumeLimitMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.redis_client = get_redis_client()
        self.lua_limiter = self.redis_client.register_script(LUA_RATE_LIMITER)

    def process_request(self, request):
        if request.path == '/api/v1/assessments/submit/' and request.method == 'POST':
            # 1. Xác thực kích thước tệp tin đầu vào từ HTTP Header
            content_length = request.META.get('CONTENT_LENGTH')
            if not content_length:
                return JsonResponse({'error': 'Length Required (Missing Content-Length)'}, status=411)
            
            try:
                incoming_bytes = int(content_length)
            except ValueError:
                return JsonResponse({'error': 'Invalid Content-Length header'}, status=400)

            # 2. Định danh đối tượng truy cập (Hỗ trợ tài khoản và tài khoản khách IP)
            user = request.user
            if not user or not user.is_authenticated:
                auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
                if auth_header and auth_header.startswith('Bearer '):
                    try:
                        token = auth_header.split(' ')[1]
                        from rest_framework_simplejwt.authentication import JWTAuthentication
                        jwt_auth = JWTAuthentication()
                        validated_token = jwt_auth.get_validated_token(token)
                        user = jwt_auth.get_user(validated_token)
                        if user:
                            request.user = user
                    except Exception as e:
                        logger.warning(f"Failed to authenticate JWT in VolumeLimitMiddleware: {e}")

            if user and user.is_authenticated:
                user_id = f"user:{user.id}"
                # Lấy tier và chuyển sang chữ hoa (FREE, PLUS, PREMIUM, PRO)
                tier_raw = getattr(user.subscription, 'tier', 'Free') if hasattr(user, 'subscription') else 'Free'
                tier = tier_raw.upper()
            else:
                # Cơ chế dự phòng dựa trên Guest ID hoặc Địa chỉ IP mạng
                # Guest ID can come from header, post body, or remote address
                guest_id = request.headers.get('X-Guest-ID')
                if not guest_id:
                    guest_id = request.POST.get('guest_id')
                identifier = guest_id if guest_id else request.META.get('REMOTE_ADDR', 'anonymous')
                user_id = f"guest:{identifier}"
                tier = 'GUEST'

            # Lưu lại rate_limit_user_id để views/tasks có thể truy cập
            request.rate_limit_user_id = user_id

            # 3. Truy vấn cấu hình giới hạn dung lượng (Bytes) từ Redis Hash
            config_key = f"config:volume:{tier}"
            try:
                limits = self.redis_client.hgetall(config_key)
            except Exception as e:
                logger.error(f"Failed to query limits from Redis: {e}")
                limits = {}

            # Giải mã bytes của hash nếu Redis client trả về bytes
            limits_decoded = {}
            for k, v in limits.items():
                k_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
                v_str = v.decode('utf-8') if isinstance(v, bytes) else str(v)
                limits_decoded[k_str] = v_str

            # Nếu bộ nhớ đệm trống, áp dụng cấu hình an toàn mặc định (Gói FREE: 2MB/phút, 20MB/giờ, 100MB/ngày)
            limit_min = int(limits_decoded.get('min', 2 * 1024 * 1024))
            limit_hr = int(limits_decoded.get('hr', 20 * 1024 * 1024))
            limit_day = int(limits_decoded.get('day', 100 * 1024 * 1024))

            # 4. Khởi tạo cấu trúc khóa đếm động cho từng đối tượng
            key_min = f"vol:{user_id}:min"
            key_hr = f"vol:{user_id}:hr"
            key_day = f"vol:{user_id}:day"

            # 5. Gọi Lua Script thực thi tính toán nguyên tử
            try:
                success, retry_after, limit_type = self.lua_limiter(
                    keys=[key_min, key_hr, key_day],
                    args=[incoming_bytes, limit_min, limit_hr, limit_day]
                )
            except Exception as e:
                logger.error(f"Error executing Lua rate limiter script: {e}")
                # Fallback to allow request in case Redis connection is broken
                return None

            # 6. Ngăn chặn yêu cầu nếu vượt quá định mức quy định
            if success == 0:
                if isinstance(limit_type, bytes):
                    limit_type = limit_type.decode('utf-8')
                retry_seconds = retry_after if retry_after > 0 else 60
                
                # Chuyển đổi loại giới hạn sang tiếng Việt
                limit_type_vn = {
                    'minute': 'phút',
                    'hour': 'giờ',
                    'day': 'ngày'
                }.get(limit_type, limit_type)

                response = JsonResponse({
                    'error': 'Too Many Requests',
                    'message': f'Tài khoản đã vượt quá giới hạn dung lượng tải tệp quy định của Gói {tier} theo khung thời gian [{limit_type_vn}].',
                    'limit_type': limit_type,
                    'retry_after_seconds': retry_seconds
                }, status=429)
                response['Retry-After'] = str(retry_seconds)
                return response

        return None


def refund_volume_limit(user_id: str, refund_bytes: int):
    """
    Hoàn trả lại số lượng bytes đã khấu trừ của người dùng trong trường hợp hệ thống 
    xử lý tác vụ thất bại do lỗi nội bộ hoặc lỗi dịch vụ máy chủ.
    """
    if not user_id or not refund_bytes or refund_bytes <= 0:
        return
    
    from core_project.ws_utils import get_redis_client
    r = get_redis_client()
    
    # Kịch bản Lua xử lý hoàn dung lượng an toàn (Atomic Refund Script)
    LUA_REFUND = """
    -- keys: KEYS[1] (min), KEYS[2] (hr), KEYS[3] (day)
    -- args: ARGV[1] (refund_bytes)

    local refund = tonumber(ARGV[1])

    for i, key in ipairs(KEYS) do
        local current = redis.call('GET', key)
        -- Chỉ thực hiện hoàn trả dung lượng nếu khóa vẫn đang tồn tại trong bộ nhớ (chưa quá hạn TTL)
        if current then
            local new_val = tonumber(current) - refund
            -- Đảm bảo dung lượng không bị âm
            if new_val < 0 then new_val = 0 end
            
            -- Cập nhật giá trị mới và duy trì nguyên vẹn thời gian sống (TTL) còn lại của khóa
            redis.call('SET', key, new_val, 'KEEPTTL') 
        end
    end

    return 1
    """
    try:
        lua_refund_executor = r.register_script(LUA_REFUND)
        
        key_min = f"vol:{user_id}:min"
        key_hr = f"vol:{user_id}:hr"
        key_day = f"vol:{user_id}:day"
        
        lua_refund_executor(keys=[key_min, key_hr, key_day], args=[refund_bytes])
        logger.info(f"Successfully refunded {refund_bytes} bytes to rate limit for user {user_id}")
    except Exception as e:
        logger.error(f"Error executing Lua refund script for {user_id}: {e}")

