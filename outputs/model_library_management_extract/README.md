# 模特库管理代码提取包

本目录是从 `toochuangai` 当前工作区提取的模特库管理代码快照（生成日期：2026-11-07）。

## 包含内容

- `model_management.py`：Flask Blueprint 后端，包含模特库、视频文件服务、模特排队和通知逻辑。模特库页面会调用排队接口，所以这里保留了整个蓝图，而不是只截取 `/api/models`。
- `templates/model_library.html`：模特库页面，支持上传、筛选、排序、编辑、删除、暂停/恢复、代排队和查看排队明细。
- `templates/model_queue.html`：模特排队总览页面，支持分页、筛选、排队、完成和取消。
- `integration_example.py`：把蓝图注册到现有 Flask 应用的最小示例。
- `requirements-model-library.txt`：该模块直接/间接需要的 Python 依赖提示。`n- `config.example.env`：不含密钥的配置键名示例，仅作宿主配置参考。
- `docs/api.md`：路由和接口说明。
- `docs/database-schema.md`：代码依赖的 SQL Server 表和字段说明（原仓库没有对应建表迁移，因此这里是按代码整理的字段契约）。
- `static/css/README.md`：说明模板引用的主题 CSS 在当前工作区缺失。

## 接入现有 Flask 项目

1. 将 `model_management.py` 放到 Flask 应用可导入的目录。
2. 将两个 HTML 文件放入 Flask 的 `templates/` 目录。
3. 保留宿主项目中的以下依赖模块：
   - `bjc.sf_db`、`bjc.dui_db`：SQL Server 查询/写入封装。
   - `department_permissions.require_permission`：页面权限装饰器。
   - `innovation.message_service.MessageService`：飞书通知。
   - `secret_settings.py` 及其数据库、飞书配置。
4. 在应用初始化处注册蓝图：

```python
from model_management import model_management_bp
app.register_blueprint(model_management_bp)
```

5. 登录态需要把当前用户名称放进 Flask session 的 `feishu_user_name`，否则数据范围和通知收件人无法正确判断。
6. 修改 `model_management.py` 顶部的 `BASE_VIDEO_DIR`，指向实际的视频存储目录。当前代码默认值是 `D:\tuchuangai\模特视频`，压缩包没有包含任何真实视频文件。

模板中的 Bootstrap、Font Awesome 使用 CDN；`model_library.html` 还引用了 `static/css/unified_theme.css`，但当前工作区不存在这个文件。页面主体仍可依赖 Bootstrap 工作，部署时可补齐该 CSS 或移除这条引用。

## 逻辑概览

### 1. 页面和权限

- `/model/library` 渲染模特库页面，并要求 `model_library` 权限。
- `/model/queue` 渲染排队总览，并要求 `model_queue` 权限。
- `/model/videos/<filename>` 从 `BASE_VIDEO_DIR` 提供视频文件。

### 2. 模特数据

模特记录存放在 SQL Server 的 `[模特信息]` 表。`GET /api/models` 会按当前用户过滤上传人，并支持姓名、状态、国家、等级、是否有排队和排序条件；查询通过子查询统计每个模特当前未完成排队数。

当前代码还保留了共享可见规则：郭云秋可额外看到曹丽霞上传的模特。上传时会对文件名执行 `secure_filename`，避免同名文件时覆盖旧文件，然后把文件名以分号写入 `视频地址` 字段；数据库插入成功后异步通知相关运营部门。

`PUT /api/models/<id>` 修改基本信息并按 `keep_videos` 清理被移除的视频；当前 PUT 路由本身没有再次校验上传人，宿主接入时应补充所有权/权限校验。`DELETE` 会校验只能删除自己上传的模特，再删除视频文件、关联排队和模特记录。

### 3. 排队数据

排队记录存放在 `[模特排队]` 表。普通排队和技术代排都会检查“同一模特 + 同一运营/部门是否已有未完成预约”，避免重复预约。查询接口返回当前排队人数、队列顺序和当前用户自己的位置。

完成、取消、暂停/恢复会更新排队状态；完成当前视频后会通知当前用户、模特上传人和下一位排队用户。暂停排队还会同步把模特状态改为“暂停拍摄”，恢复时改回“合作中”。

### 4. 外部依赖和现有边界

该提取包是“接回原项目”的代码包，不是完全脱离原项目即可启动的独立应用。数据库连接、登录态、权限和飞书消息仍由宿主项目提供。原实现使用字符串拼接 SQL，接入时建议继续沿用现有数据库封装并逐步改为参数化查询。

当前若干数据/排队 API 没有单独加 `require_permission` 装饰器，主要依赖登录态、上传人和业务条件控制；`/api/models_all` 还是全量查询。若部署环境需要严格权限隔离，应在宿主应用或蓝图层补充接口级鉴权。

