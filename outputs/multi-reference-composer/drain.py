import json
from 图片.request_limits import get_request_limiter
limiter=get_request_limiter()
limiter.drain(True)
print(json.dumps(limiter.snapshot(),ensure_ascii=False))
