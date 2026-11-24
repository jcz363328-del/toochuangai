import json,time
from 图片.request_limits import get_request_limiter
quiet=0
for attempt in range(16):
    snapshot=get_request_limiter().snapshot()
    if snapshot['active']==0 and snapshot['waiting']==0:
        quiet+=1
        if quiet>=5:
            print('No active or waiting provider requests for 12 seconds.')
            break
    else:
        quiet=0
    time.sleep(3)
else:
    print(json.dumps(snapshot,ensure_ascii=False))
    raise SystemExit(2)
