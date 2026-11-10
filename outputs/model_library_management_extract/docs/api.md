# API 速查

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/model/library` | 模特库页面 |
| GET | `/model/queue` | 模特排队总览页面 |
| GET | `/model/videos/<filename>` | 读取视频文件 |
| GET/POST | `/api/models` | 查询/新增模特；GET 支持姓名、状态、国家、等级、queue_filter、sort |
| GET | `/api/models_all` | 查询全部模特记录 |
| GET | `/api/model_queue_overview` | 分页查询排队总览 |
| PUT/DELETE | `/api/models/<model_id>` | 修改/删除模特及视频 |
| GET | `/api/model_queue/<model_id>` | 查询单个模特的未完成队列 |
| POST | `/api/model_queue` | 当前用户为模特排队 |
| POST | `/api/model_queue/proxy` | 技术代运营姓名排队 |
| POST | `/api/model_queue/<model_id>/complete_mine` | 当前用户完成自己的排队 |
| POST | `/api/model_queue/<queue_id>/complete` | 完成指定排队并触发通知 |
| POST | `/api/model_queue/<queue_id>/cancel` | 取消指定排队 |
| POST | `/api/model_queue/<model_id>/cancel_mine` | 当前用户取消自己的排队 |
| POST | `/api/models/<model_id>/pause` | 暂停/恢复当前用户排队 |
| POST | `/api/models/<model_id>/proxy` | 设置当前未完成排队的代排标记 |

上传接口使用 `multipart/form-data`，字段包括 `code`、`name`、`status`、`country`、`level`、`remark` 和多文件字段 `videos`。排队接口使用 JSON。
