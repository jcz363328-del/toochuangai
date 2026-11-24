# 小哈并发控制

网页后台任务与画布请求统一经过 `图片/request_limits.py`。两个服务使用同一持久化目录下的 `history/request_limits.sqlite3`，限流计数跨进程共享。SQLite 仅保存调度信息，不保存提示词、密钥或图片。

默认参数：

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| XIAOHA_JOB_WORKERS | 4 | 后台执行线程数 |
| XIAOHA_JOB_QUEUE_LIMIT | 64 | 后台任务总容量 |
| XIAOHA_ACCOUNT_QUEUE_LIMIT | 8 | 每个账号的后台任务容量 |
| XIAOHA_CANVAS_MAX_REQUESTS | 8 | 画布模型请求入口容量 |
| XIAOHA_MODEL_CONCURRENCY | 6 | 模型接口合计并发 |
| XIAOHA_OMNIA_CONCURRENCY | 2 | OmniaKey 生图和文字合计并发 |
| XIAOHA_OMNIA_IMAGE_CONCURRENCY | 1 | OmniaKey 生图并发 |
| XIAOHA_OMNIA_TEXT_CONCURRENCY | 2 | OmniaKey 文字分析并发 |
| XIAOHA_ARK_CONCURRENCY | 2 | Ark 并发 |
| XIAOHA_JIMENG_CONCURRENCY | 1 | 即梦任务并发 |
| XIAOHA_DOWNLOAD_CONCURRENCY | 6 | 图片下载并发 |
| XIAOHA_MAX_WAITING | 64 | 接口等待队列容量 |
| XIAOHA_QUEUE_TIMEOUT | 900 | 接口排队超时秒数 |

模型槽位覆盖创建、轮询及结果获取整个过程。提交结果不明时不会自动新建付费任务，槽位保留 60 秒后释放；429 会触发共享冷却。这不能保证上游任务一定成功，也无法在同步接口失联后确定远端实际结束时间。

维护时可以调用 `get_request_limiter().drain(True)` 拒绝新任务；已经接收的后台或画布多阶段任务允许继续。**不能只凭 limiter.snapshot() 的 active=0 就重启**：还必须确认后台任务队列、处理线程与画布请求均已结束。完成维护务必 `drain(False)`。

更新后已打开的画布需要刷新，以重新载入后端代理配置。代理仅调用 OmniaKey，不使用 OpenRouter。
