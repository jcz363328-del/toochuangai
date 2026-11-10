# 模特库管理模块

这是 `toochuangai` 主 Flask 应用中的“模特库管理 / 模特排队”功能打包版，不是独立应用。包内包含蓝图后端和两个页面模板，便于迁移到同类 Flask 项目。

## 包含内容

- `model_management.py`：蓝图、模特信息查询/新增/编辑/删除、视频文件服务、排队/暂停/取消/完成/代排队接口。
- `templates/model_library.html`：模特库页面。
- `templates/model_queue.html`：模特排队页面。

## 依赖与前置条件

1. Python 3.10+、Flask、Werkzeug，以及项目现有 `requirements.txt` 中的依赖。
2. 项目已有以下模块和能力：
   - `bjc.sf_db(sql, single=False)`：查询数据库。
   - `bjc.dui_db(sql)`：执行写入/更新/删除。
   - `department_permissions.require_permission(name)`：权限装饰器。
   - `innovation.message_service.MessageService`：飞书消息通知（可按项目实际情况替换）。
3. SQL Server 中存在表 `[模特信息]`、`[模特排队]` 和 `feishu_id`。
4. Flask 的 `templates` 目录可加载两个模板；登录态中包含 `session['feishu_user_name']`。
5. 服务器可访问视频目录。默认路径为 `D:\tuchuangai\模特视频`，迁移时请修改 `model_management.py` 顶部的 `BASE_VIDEO_DIR`。

## 接入步骤

1. 将 `model_management.py` 放到 Flask 项目根目录（或调整导入路径）。
2. 将两个 HTML 文件复制到项目的 `templates/` 目录。
3. 在应用初始化位置注册蓝图：

   ```python
   from model_management import model_management_bp
   app.register_blueprint(model_management_bp)
   ```

4. 确认权限系统包含 `model_library` 和 `model_queue` 两个权限标识，并给目标用户授权。
5. 启动主应用后访问：
   - `/model/library`：查看、筛选、新增和维护模特。
   - `/model/queue`：查看排队概览并执行排队操作。

## 主要接口

- `GET/POST /api/models`：当前用户可见的模特列表 / 新增模特及视频。
- `GET /api/models_all`：全部模特列表（请按实际权限需求限制）。
- `PUT/DELETE /api/models/<model_id>`：编辑或删除模特。
- `GET /api/model_queue/<model_id>`：查看某模特排队信息。
- `POST /api/model_queue`：创建排队。
- `POST /api/model_queue/proxy`：代排队。
- `POST /api/model_queue/<queue_id>/complete`：完成排队。
- `POST /api/model_queue/<queue_id>/cancel`：取消排队。
- `POST /api/models/<model_id>/pause`：暂停/恢复排队。
- `/model/videos/<filename>`：视频文件访问地址。

## 使用流程

1. 打开“模特库”，填写模特编号、姓名、状态、国家、等级、备注并上传视频。
2. 在模特卡片中查看视频和当前排队数量。
3. 点击排队，选择部门并提交；需要代操作时使用代排队功能。
4. 在“模特排队”页面查看自己的排队、处理暂停/取消/完成。
5. 新增模特和关键排队状态变化会尝试发送飞书通知；通知失败不会阻断数据库操作。

## 安全注意事项

- 不要把 `.env`、数据库密码、飞书凭证或真实视频素材放进 ZIP。
- 生产环境建议将 SQL 改为参数化查询，并给 `models_all`、视频访问接口补充登录/权限校验。
- `BASE_VIDEO_DIR` 应指向受控目录，并配置上传大小、扩展名和文件名策略。
- 当前包按原项目代码打包，未改变业务逻辑。
