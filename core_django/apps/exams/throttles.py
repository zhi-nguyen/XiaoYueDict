import time
import logging
from rest_framework.throttling import BaseThrottle
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Kịch bản Lua: Xử lý nguyên tử cơ chế Cửa sổ trượt (Sliding Window), chống nhiễm độc ZSET
LUA_BEHAVIORAL_SLIDING_LIMITER = """
local key = KEYS[1]
local exam_id = ARGV[1]
local limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- 1. Dọn dẹp các bản ghi cũ nằm ngoài cửa sổ trượt (Sliding Window)
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

-- 2. Kiểm tra trạng thái tồn tại của đề thi trong khung thời gian hiện tại
local current_score = redis.call('ZSCORE', key, exam_id)
local current_cardinality = redis.call('ZCARD', key)

-- 3. Đánh chặn nếu là đề thi mới và số lượng đề độc bản đã chạm định mức tối đa
if not current_score and current_cardinality >= limit then
    -- Trích xuất phần tử cũ nhất để tính toán chính xác thời gian hồi (Retry-After)
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = window
    if oldest[2] then
        retry_after = window - (now - tonumber(oldest[2]))
    end
    -- Trả về 0 (Từ chối) kèm thời gian chờ động, tuyệt đối không ghi nhận exam_id vào Set
    return {0, math.ceil(retry_after)}
end

-- 4. Nếu hợp lệ, tiến hành thêm mới hoặc cập nhật timestamp cho đề thi
redis.call('ZADD', key, now, exam_id)
redis.call('EXPIRE', key, window)

return {1, 0} -- Trả về 1 xác nhận yêu cầu thành công
"""

class UniqueExamAccessThrottle(BaseThrottle):
    def __init__(self):
        self.window = 60  # Cửa sổ thời gian theo dõi: 60 giây
        self.limit = 3    # Định mức tối đa: 3 đề thi khác biệt

    def get_ident(self, request):
        if request.user and request.user.is_authenticated:
            return f"user_{request.user.id}"
        
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            ip = xff.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return f"ip_{ip}"

    def allow_request(self, request, view):
        if view.action not in ['retrieve', 'full_exam']:
            return True

        exam_id = view.kwargs.get('pk')
        if not exam_id:
            return True

        ident = self.get_ident(request)
        redis_key = f"throttle:unique_exams:{ident}"
        now = time.time()

        try:
            # Truy xuất native Redis client từ Cache Backend của Django
            redis_client = cache.client.get_client()
            
            # Đăng ký và thực thi Kịch bản Lua nguyên tử
            script = redis_client.register_script(LUA_BEHAVIORAL_SLIDING_LIMITER)
            success, retry_after = script(keys=[redis_key], args=[str(exam_id), self.limit, self.window, now])
            
            if success == 0:
                # Thiết lập thời gian chờ động để phương thức wait() truy xuất
                self.dynamic_retry_after = retry_after
                logger.warning(f"[Anti-Scraping] Chặn tài khoản/IP: {ident} truy xuất đề thi vượt tần suất.")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Lỗi hệ thống tại UniqueExamAccessThrottle: {e}")
            # Fail-open: Đảm bảo hệ thống không bị đóng băng gián đoạn nếu dịch vụ Redis gặp trục trặc
            return True 

    def wait(self):
        """
        Trích xuất số giây người dùng cần chờ trước khi được phép truy cập tài nguyên mới.
        """
        return getattr(self, 'dynamic_retry_after', self.window)
